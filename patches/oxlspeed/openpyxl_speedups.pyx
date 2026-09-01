# cython: language_level=3, binding=True, boundscheck=False, wraparound=False
"""Generic native speedups for openpyxl 3.1.x hot per-cell paths.

Semantics-identical replacements for the functions that run once per cell
on every non-write-only load (2.5M times for a 100k-row workbook):

- coordinate_to_tuple          — "AF123" -> (123, 32), single scan
- WorkSheetParser.parse_cell   — XML element -> cell dict (also used by the
                                  read_only path via stock parse_row)
- WorksheetReader.bind_cells   — FUSED native loop: iterparse + row handling
                                  (row counter / row_dimensions side effects)
                                  + single-pass cell child scan (v/f/is in one
                                  sweep instead of three find/findtext scans)
                                  + direct Cell construction. No per-cell dict,
                                  no per-cell Python method call.

No workbook structure awareness: every sheet and cell of any workbook takes
the same code path. Unusual content (formulas, dates, rich text, inline
strings, booleans) delegates to the very same openpyxl helpers the stock
implementation uses, so behaviour is preserved exactly.
"""

import gc
from warnings import warn

from openpyxl.cell.cell import Cell
from openpyxl.cell.text import Text
from openpyxl.styles.cell_style import StyleArray
from openpyxl.utils.datetime import from_excel, from_ISO8601
from openpyxl.worksheet._reader import (
    VALUE_TAG, FORMULA_TAG, INLINE_STRING, ROW_TAG, COL_TAG, PROT_TAG,
    EXT_TAG, CF_TAG, LEGACY_TAG, ROW_BREAK_TAG, COL_BREAK_TAG,
    CUSTOM_VIEWS_TAG, PRINT_TAG, MARGINS_TAG, PAGE_TAG, HEADER_TAG,
    FILTER_TAG, VALIDATION_TAG, PROPERTIES_TAG, VIEWS_TAG, FORMAT_TAG,
    SCENARIOS_TAG, TABLE_TAG, HYPERLINK_TAG, MERGE_TAG,
    _cast_number, parse_richtext_string, iterparse,
)
from openpyxl.worksheet.page import PageMargins, PrintOptions, PrintPageSetup
from openpyxl.worksheet.header_footer import HeaderFooter
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.datavalidation import DataValidationList
from openpyxl.worksheet.properties import WorksheetProperties
from openpyxl.worksheet.views import SheetViewList
from openpyxl.worksheet.dimensions import SheetFormatProperties
from openpyxl.worksheet.scenario import ScenarioList
from openpyxl.worksheet.table import TablePartList
from openpyxl.worksheet.hyperlink import HyperlinkList
from openpyxl.worksheet.merge import MergeCells

# column_index_from_string("ZZZ") == 18278; 0 and 18279+ are invalid
_MAX_COLUMN = 18278


def coordinate_to_tuple(str coordinate):
    """Stock-equivalent "AF123" -> (123, 32) in a single scan."""
    cdef Py_ssize_t n = len(coordinate)
    cdef Py_ssize_t i, row_start = -1
    cdef long col = 0, o
    if n == 0:
        # stock raises NameError on unbound idx here; nobody reaches it via
        # parse_cell (empty coordinate is falsy) — ValueError is fine
        raise ValueError("coordinate string cannot be empty")
    for i in range(n):
        if '0' <= coordinate[i] <= '9':
            row_start = i
            break
    if row_start < 0:
        row_start = n - 1  # mirrors enumerate() exhaustion in stock helper
    col_str = coordinate[:row_start]
    if len(col_str) > 3:
        raise ValueError(
            f"'{col_str}' is not a valid column name. "
            "Column names are from A to ZZZ")
    for i in range(len(col_str)):
        o = ord(col_str[i])
        if 97 <= o <= 122:  # a-z -> A-Z
            o -= 32
        if o < 65 or o > 90:
            raise ValueError(
                f"'{col_str}' is not a valid column name. "
                "Column names are from A to ZZZ")
        col = col * 26 + (o - 64)
    if not 0 < col <= _MAX_COLUMN:
        raise ValueError(
            f"'{col_str}' is not a valid column name. "
            "Column names are from A to ZZZ")
    return int(coordinate[row_start:]), col


def parse_cell(self, element):
    """Stock-equivalent WorkSheetParser.parse_cell (kept for the read_only
    path and any external caller; the fused bind_cells inlines it)."""
    data_type = element.get('t', 'n')
    coordinate = element.get('r')
    style_id = element.get('s', 0)
    if style_id:
        style_id = int(style_id)

    if data_type == "inlineStr":
        value = None
    else:
        value = element.findtext(VALUE_TAG, None)
        if not value:
            value = None

    if coordinate:
        row, column = coordinate_to_tuple(coordinate)
        self.col_counter = column
    else:
        self.col_counter = self.col_counter + 1
        row = self.row_counter
        column = self.col_counter

    if not self.data_only and element.find(FORMULA_TAG) is not None:
        data_type = 'f'
        value = self.parse_formula(element)

    elif value is not None:
        if data_type == 'n':
            value = _cast_number(value)
            if style_id in self.date_formats:
                data_type = 'd'
                try:
                    value = from_excel(
                        value, self.epoch,
                        timedelta=style_id in self.timedelta_formats)
                except (OverflowError, ValueError):
                    warn(f"Cell {coordinate} is marked as a date but the serial value "
                         f"{value} is outside the limits for dates. The cell will be "
                         f"treated as an error.")
                    data_type = "e"
                    value = "#VALUE!"
        elif data_type == 's':
            value = self.shared_strings[int(value)]
        elif data_type == 'b':
            value = bool(int(value))
        elif data_type == "str":
            data_type = "s"
        elif data_type == 'd':
            value = from_ISO8601(value)

    elif data_type == "inlineStr":
        child = element.find(INLINE_STRING)
        if child is not None:
            data_type = 's'
            if self.rich_text:
                value = parse_richtext_string(child)
            else:
                value = Text.from_tree(child).content

    return {'row': row, 'column': column, 'value': value,
            'data_type': data_type, 'style_id': style_id}


def bind_cells(self):
    """Stock-equivalent WorksheetReader.bind_cells as a fused native loop.

    Transliterates WorkSheetParser.parse() (tag dispatch incl. all sheet
    structure side effects), parse_row (row counter / row_dimensions) and
    parse_cell (single-pass v/f/is child scan) into one compiled loop that
    constructs the same openpyxl Cell objects (same slots end-state incl.
    the per-cell StyleArray copy) directly into ws._cells.

    The loop disables the cyclic GC while running: it allocates millions of
    long-lived objects and no cycles, so periodic gen0/1 scans over the
    growing heap are pure overhead (the GC state is restored afterwards).
    """
    ws = self.ws
    parser = self.parser
    styles = ws.parent._cell_styles
    cells = ws._cells
    new = Cell.__new__

    gc_enabled = gc.isenabled()
    if gc_enabled:
        gc.disable()
    try:
        dispatcher = {
            COL_TAG: parser.parse_column_dimensions,
            PROT_TAG: parser.parse_sheet_protection,
            EXT_TAG: parser.parse_extensions,
            CF_TAG: parser.parse_formatting,
            LEGACY_TAG: parser.parse_legacy,
            ROW_BREAK_TAG: parser.parse_row_breaks,
            COL_BREAK_TAG: parser.parse_col_breaks,
            CUSTOM_VIEWS_TAG: parser.parse_custom_views,
        }
        properties = {
            PRINT_TAG: ('print_options', PrintOptions),
            MARGINS_TAG: ('page_margins', PageMargins),
            PAGE_TAG: ('page_setup', PrintPageSetup),
            HEADER_TAG: ('HeaderFooter', HeaderFooter),
            FILTER_TAG: ('auto_filter', AutoFilter),
            VALIDATION_TAG: ('data_validations', DataValidationList),
            PROPERTIES_TAG: ('sheet_properties', WorksheetProperties),
            VIEWS_TAG: ('views', SheetViewList),
            FORMAT_TAG: ('sheet_format', SheetFormatProperties),
            SCENARIOS_TAG: ('scenarios', ScenarioList),
            TABLE_TAG: ('tables', TablePartList),
            HYPERLINK_TAG: ('hyperlinks', HyperlinkList),
            MERGE_TAG: ('merged_cells', MergeCells),
        }

        row_dimensions = parser.row_dimensions
        data_only = parser.data_only
        it = iterparse(parser.source)

        for _, element in it:
            tag = element.tag
            handler = dispatcher.get(tag)
            if handler is not None:
                handler(element)
                element.clear()
                continue
            prop = properties.get(tag)
            if prop is not None:
                setattr(parser, prop[0], prop[1].from_tree(element))
                element.clear()
                continue
            if tag != ROW_TAG:
                continue

            # ---- fused parse_row ----
            attrs = dict(element.attrib)
            if 'r' in attrs:
                try:
                    parser.row_counter = int(attrs['r'])
                except ValueError:
                    val = float(attrs['r'])
                    if val.is_integer():
                        parser.row_counter = int(val)
                    else:
                        raise ValueError(
                            f"{attrs['r']} is not a valid row number")
            else:
                parser.row_counter += 1
            parser.col_counter = 0
            keys = {k for k in attrs if not k.startswith('{')}
            if keys - {'r', 'spans'}:
                row_dimensions[str(parser.row_counter)] = attrs
            rc = parser.row_counter

            # ---- fused parse_cell + bind, single pass over cell children ----
            for el in element:
                data_type = el.get('t', 'n')
                coordinate = el.get('r')
                style_id = el.get('s', 0)
                if style_id:
                    style_id = int(style_id)

                v_text = None
                has_f = False
                is_child = None
                for ch in el:
                    ctag = ch.tag
                    if ctag == VALUE_TAG:
                        v_text = ch.text
                    elif ctag == FORMULA_TAG:
                        has_f = True
                    elif ctag == INLINE_STRING:
                        is_child = ch

                if data_type == 'inlineStr':
                    value = None
                else:
                    value = v_text
                    if not value:
                        value = None

                if coordinate:
                    row, column = coordinate_to_tuple(coordinate)
                    parser.col_counter = column
                else:
                    parser.col_counter += 1
                    row = rc
                    column = parser.col_counter

                if not data_only and has_f:
                    data_type = 'f'
                    value = parser.parse_formula(el)

                elif value is not None:
                    if data_type == 'n':
                        value = _cast_number(value)
                        if style_id in parser.date_formats:
                            data_type = 'd'
                            try:
                                value = from_excel(
                                    value, parser.epoch,
                                    timedelta=style_id in parser.timedelta_formats)
                            except (OverflowError, ValueError):
                                warn(f"Cell {coordinate} is marked as a date but "
                                     f"the serial value {value} is outside the "
                                     f"limits for dates. The cell will be treated "
                                     f"as an error.")
                                data_type = "e"
                                value = "#VALUE!"
                    elif data_type == 's':
                        value = parser.shared_strings[int(value)]
                    elif data_type == 'b':
                        value = bool(int(value))
                    elif data_type == "str":
                        data_type = "s"
                    elif data_type == 'd':
                        value = from_ISO8601(value)

                elif data_type == "inlineStr":
                    if is_child is not None:
                        data_type = 's'
                        if parser.rich_text:
                            value = parse_richtext_string(is_child)
                        else:
                            value = Text.from_tree(is_child).content

                c = new(Cell)
                c.parent = ws
                c.row = row
                c.column = column
                c._value = value
                c.data_type = data_type
                c._style = StyleArray(styles[style_id])
                c._hyperlink = None
                c._comment = None
                cells[(row, column)] = c

            element.clear()
    finally:
        if gc_enabled:
            gc.enable()

    if cells:
        ws._current_row = ws.max_row
