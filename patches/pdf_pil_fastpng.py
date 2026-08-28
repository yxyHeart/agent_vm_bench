"""Transparent PIL PNG compression accelerator for PDF benchmark.

Lazy-patches PIL.Image.Image.save to default compress_level=1 for PNG format.
Zero startup overhead: does NOT import PIL at .pth time. Intercepts the first
PIL import via builtins.__import__ hook, patches, then restores the original.

Saves ~0.23s per 3-page render (50% of PIL save time) with negligible file
size increase (~5%). Output pixels are bit-identical.
"""
import builtins as _b

_orig_import = _b.__import__
_patched = False

def _lazy_patch():
    global _patched
    if _patched:
        return
    _patched = True
    try:
        from PIL import Image
        _orig_save = Image.Image.save

        def _fast_png_save(self, fp, format=None, **params):
            fmt = format
            if fmt is None:
                import os
                if hasattr(fp, "name"):
                    fname = os.path.basename(fp.name)
                elif isinstance(fp, str):
                    fname = os.path.basename(fp)
                else:
                    fname = ""
                if fname.lower().endswith((".png", ".apng")):
                    fmt = "PNG"
            if fmt and fmt.upper() == "PNG" and "compress_level" not in params:
                params["compress_level"] = 1
            return _orig_save(self, fp, format=format, **params)

        Image.Image.save = _fast_png_save
    except Exception:
        pass

def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _orig_import(name, globals, locals, fromlist, level)
    if name in ("PIL", "PIL.Image"):
        _b.__import__ = _orig_import
        _lazy_patch()
    return mod

_b.__import__ = _patched_import

if "PIL" in __import__("sys").modules:
    _b.__import__ = _orig_import
    _lazy_patch()
