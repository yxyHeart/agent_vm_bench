"""Bootstrap for openpyxl_speedups: installs the compiled replacements the
moment openpyxl is first imported, with zero cost for processes that never
touch openpyxl (a lazy meta-path hook instead of an eager import).

Disable with OPENPYXL_SPEEDUPS=0 (A/B attribution).
"""
import os
import sys

_TARGET = "openpyxl"

if os.environ.get("OPENPYXL_SPEEDUPS", "1") == "1" and _TARGET not in sys.modules:
    import importlib.machinery

    class _PatchLoader:
        def __init__(self, real):
            self.real = real

        def create_module(self, spec):
            return self.real.create_module(spec)

        def exec_module(self, module):
            self.real.exec_module(module)
            try:
                _patch()
            except Exception:
                pass  # never break openpyxl; stock paths keep running

    class _Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname != _TARGET:
                return None
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.loader is None:
                return None
            spec.loader = _PatchLoader(spec.loader)
            return spec

    def _patch():
        import openpyxl
        # the fused loop transliterates 3.1.5 internals line by line;
        # any other version must keep stock behaviour
        if openpyxl.__version__ != "3.1.5":
            return
        import openpyxl_speedups as sp
        from openpyxl.worksheet import _reader
        _reader.WorkSheetParser.parse_cell = sp.parse_cell
        _reader.WorksheetReader.bind_cells = sp.bind_cells
        _reader.coordinate_to_tuple = sp.coordinate_to_tuple
        import openpyxl.utils.cell
        openpyxl.utils.cell.coordinate_to_tuple = sp.coordinate_to_tuple

    sys.meta_path.insert(0, _Finder())
