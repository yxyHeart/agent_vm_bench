#!/bin/bash
# Close the evidence hole: prove the save product consumed a CACHE-HIT-loaded
# workbook (explicit [oxlcache] HIT debug line), and complete the save matrix
# with speedups-only (MISS, no cache). Compare against the archived stock save.
set -u
cd /w

echo "=== 1. stock save (reference, no cache) ==="
OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0 python3 save.py /w/out_stock_ref.xlsx 2>&1 | grep -E "SAVEDIGEST|oxlcache" 

echo "=== 2. speedups-only save (MISS parse, no cache) ==="
OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=1 python3 save.py /w/out_speedups.xlsx 2>&1 | grep -E "SAVEDIGEST|oxlcache"

echo "=== 3. combo: fill cache, then save with debug (expect HIT then save) ==="
rm -rf /tmp/oxlcache
OPENPYXL_CACHE_DEBUG=1 python3 -c "
from openpyxl import load_workbook
wb = load_workbook('/opt/document-bench/xlsx/input/monthly_operations_template.xlsx', data_only=False)
wb.close()
" 2>&1 | grep oxlcache
OPENPYXL_CACHE_DEBUG=1 python3 save.py /w/out_combo_hit_dbg.xlsx 2>&1 | grep -E "SAVEDIGEST|oxlcache"

echo "=== 4. member-level comparison (excluding docProps/core.xml) ==="
python3 - <<'PY'
import hashlib, zipfile

def members(p):
    z = zipfile.ZipFile(p)
    return {n: hashlib.md5(z.read(n)).hexdigest()[:10] for n in sorted(z.namelist())}

def cmp(a_name, a, b_name, b):
    ka, kb = set(a), set(b)
    assert ka == kb, f"member list differs: {ka ^ kb}"
    diff = [k for k in a if a[k] != b[k]]
    diff_nostamp = [k for k in diff if k != "docProps/core.xml"]
    print(f"{a_name} vs {b_name}: {len(a)} members, differing={diff}, "
          f"excluding timestamp member={diff_nostamp} -> {'IDENTICAL' if not diff_nostamp else 'REAL DIFF'}")

S = members("/w/out_stock_ref.xlsx")
B = members("/w/out_speedups.xlsx")
C = members("/w/out_combo_hit_dbg.xlsx")
cmp("stock      ", S, "speedups(MISS)", B)
cmp("stock      ", S, "combo(HIT)   ", C)
cmp("speedups   ", B, "combo(HIT)   ", C)
PY
echo SAVE-MATRIX-DONE
