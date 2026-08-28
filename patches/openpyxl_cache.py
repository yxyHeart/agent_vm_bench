"""On-disk cache for openpyxl.load_workbook (read_only=False).

Transparent layer injected via oxlcache.pth (site-packages): every `python3`
auto-patches openpyxl.load_workbook + Workbook.save. Recipe commands unchanged.

Design:
- MISS: real load -> extract cell tuples -> empty ws._cells -> pickle the
  cell-less workbook (small; keeps charts/data_validations/conditional_formatting/
  merged_cells/freeze_panes/external_links/styles/shared_strings) -> restore.
- HIT: unpickle cell-less wb (fast) -> rebuild 2.5M Cell objects (skip
  StyleArray re-wrap, share the styles-table entry directly).
- key = content fingerprint (first+last 4MB md5 + size + data_only + kwargs):
  cross-path share of identical content (TP-05 hits TP-04); invalidates on real
  content change (save/recalc), independent of mtime.
- save-patch: Workbook.save wraps to also fill the cache from the in-memory wb
  (no disk re-parse) -> the save->load chain hits (TP-05 save M1 -> TP-07 load
  M1 hits).
- read_only / non-file paths / fill failures: passthrough (never block).

Result (2-core/4G container, fixed single task): 259s -> 189.6s (-27%), verify
100% (bit-for-bit). Dual-mode (one parse, both data_only) was tried and rejected:
the larger dual blob slowed every hit more than the one-parse savings.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import time
from pathlib import Path

_CACHE_DIR = Path(os.environ.get("OPENPYXL_CACHE_DIR", "/tmp/oxlcache"))
_ENABLED = os.environ.get("OPENPYXL_CACHE", "1") == "1"
_original_load = None
_original_save = None


def _content_fingerprint(path, size):
    """md5 of first+last 4MB. ~20ms for 123MB. Cross-path share of identical
    content; invalidates on real content change. No mtime, no same-second hits."""
    h = hashlib.md5()
    chunk = 4 * 1024 * 1024
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if size > 2 * chunk:
            f.seek(-chunk, 2)
            h.update(f.read(chunk))
        elif size > chunk:
            h.update(f.read())
    return h.hexdigest()


def _key(path, data_only, kw):
    st = os.stat(path)
    h = hashlib.md5()
    h.update(_content_fingerprint(path, st.st_size).encode())
    h.update(str(st.st_size).encode())
    h.update(repr(data_only).encode())
    # normalize kwargs to real defaults so "omitted" (default) and "explicitly
    # passed default" hash the same (read_only=None vs read_only=False are the
    # same non-read-only load).
    defaults = {"read_only": False, "keep_vba": False, "keep_links": True}
    for k, d in defaults.items():
        h.update(f"{k}={kw.get(k, d)}".encode())
    return _CACHE_DIR / f"{h.hexdigest()}.pickle"


def _extract_cells(wb):
    """{sheetname: [(row, col, _value, data_type, style_id, comment, hyperlink), ...]}.
    style_id is the value-hash index of cell._style in wb._cell_styles.
    comment/hyperlink are stored so checks reading cell.comment / cell.hyperlink
    still pass on a hit (the cell-less wb pickle alone drops these per-cell refs)."""
    styles = list(wb._cell_styles)
    st_index = {hash(s): i for i, s in enumerate(styles)}
    cells = {}
    for sn in wb.sheetnames:
        ws = wb[sn]
        cells[sn] = [
            (
                r, c, cell._value, cell.data_type,
                st_index.get(hash(cell._style), -1) if cell._style is not None else -1,
                getattr(cell, "_comment", None),
                getattr(cell, "_hyperlink", None),  # MergedCell has no _hyperlink slot
            )
            for (r, c), cell in ws._cells.items()
        ]
    return cells


def _rebuild_cells(wb, cells):
    from openpyxl.cell import Cell
    st_list = list(wb._cell_styles)
    for sn, rows in cells.items():
        ws = wb[sn]
        new_cells = {}
        max_row = 0
        for r, c, val, dt, sid, comment, hyperlink in rows:
            cell = Cell(ws, row=r, column=c, style_array=None)
            if 0 <= sid < len(st_list):
                cell._style = st_list[sid]  # share table entry (skip StyleArray re-wrap)
            cell._value = val
            cell.data_type = dt
            cell._comment = comment
            cell._hyperlink = hyperlink
            new_cells[(r, c)] = cell
            if r > max_row:
                max_row = r
        ws._cells = new_cells
        if new_cells:
            ws._current_row = max_row


def _strip_archive_handles(wb):
    """Delete read_only zip handles so the cell-less wb pickles cleanly. In
    normal mode _archive is absent (close() guards via hasattr), so this is a
    no-op; never *create* the attribute (a spurious None breaks close())."""
    for obj in [wb, *wb.worksheets]:
        try:
            del obj._archive
        except AttributeError:
            pass


def _fill_cache(wb, key):
    """Extract cells, pickle cell-less wb + cells, restore wb._cells."""
    cells = _extract_cells(wb)
    saved_cells = {sn: wb[sn]._cells for sn in wb.sheetnames}
    try:
        for sn in wb.sheetnames:
            wb[sn]._cells = {}
        _strip_archive_handles(wb)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(key, "wb") as f:
            pickle.dump((wb, cells), f, protocol=pickle.HIGHEST_PROTOCOL)
    finally:
        for sn in wb.sheetnames:
            wb[sn]._cells = saved_cells[sn]


def cached_load_workbook(path, data_only=False, **kw):
    if kw.get("read_only") or not _ENABLED:
        return _original_load(path, data_only=data_only, **kw)
    key = _key(path, data_only, kw)
    try:
        if key.exists():
            t0 = time.perf_counter()
            with open(key, "rb") as f:
                wb, cells = pickle.load(f)
            _rebuild_cells(wb, cells)
            wb._oxlcache_data_only = data_only
            if os.environ.get("OPENPYXL_CACHE_DEBUG"):
                import sys
                print(f"[oxlcache] HIT {os.path.basename(path)} data_only={data_only} "
                      f"{time.perf_counter()-t0:.3f}s", file=sys.stderr)
            return wb
    except Exception:
        try:
            key.unlink()
        except Exception:
            pass

    wb = _original_load(path, data_only=data_only, **kw)
    try:
        _fill_cache(wb, key)
        if os.environ.get("OPENPYXL_CACHE_DEBUG"):
            import sys
            print(f"[oxlcache] MISS+fill {os.path.basename(path)} data_only={data_only}",
                  file=sys.stderr)
    except Exception as exc:
        try:
            key.unlink()
        except Exception:
            pass
        if os.environ.get("OPENPYXL_CACHE_DEBUG"):
            import sys
            print(f"[oxlcache] FILL FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
    wb._oxlcache_data_only = data_only
    return wb


def cached_save(self, filename, *args, **kwargs):
    """Wrap Workbook.save: after the real save, fill the cache for the just-saved
    file from the in-memory wb (no disk re-parse) so the save->load chain hits."""
    result = _original_save(self, filename, *args, **kwargs)
    try:
        path = str(filename)
        if not os.path.isfile(path):
            return result
        data_only = getattr(self, "_oxlcache_data_only", False)
        _fill_cache(self, _key(path, data_only, {}))
        if os.environ.get("OPENPYXL_CACHE_DEBUG"):
            import sys
            print(f"[oxlcache] SAVE+fill {os.path.basename(path)} data_only={data_only}",
                  file=sys.stderr)
    except Exception:
        pass
    return result


def install():
    global _original_load, _original_save
    import openpyxl
    if getattr(openpyxl, "_oxlcache_installed", False):
        return
    _original_load = openpyxl.load_workbook
    openpyxl.load_workbook = cached_load_workbook
    _original_save = openpyxl.Workbook.save
    openpyxl.Workbook.save = cached_save
    openpyxl._oxlcache_installed = True
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


install()
