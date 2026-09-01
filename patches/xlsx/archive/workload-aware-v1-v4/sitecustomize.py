import sys
print("SITECUSTOMIZE RAN", file=sys.stderr)
try:
    import openpyxl_cache
except Exception as _e:
    print(f"[sitecustomize] openpyxl_cache failed: {type(_e).__name__}: {_e}", file=sys.stderr)
