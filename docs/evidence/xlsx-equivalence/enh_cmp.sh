#!/bin/bash
set -u
echo "=== docProps/core.xml 内容对比 (stock save1 vs save2) ==="
python3 - <<'PY'
import zipfile
for f in ("/w/out_stock1.xlsx", "/w/out_stock2.xlsx"):
    print(f, "->", zipfile.ZipFile(f).read("docProps/core.xml").decode()[:300].replace("\n"," "))
PY

echo "=== TP-07 真实增强链: stock vs combo(HIT) ==="
for mode in stock combo; do
  W=/w/enh_$mode
  rm -rf $W && mkdir -p $W/output && cd $W
  cp -a /opt/document-bench/xlsx/input ./input
  cp input/monthly_operations_template.xlsx output/monthly_operations_report.xlsx
  cp /h/equiv_real_enhance.py enhance_workbook.py
  if [ $mode = combo ]; then
    python3 -c "from openpyxl import load_workbook; wb=load_workbook('output/monthly_operations_report.xlsx', data_only=False); wb.close()" 2>/dev/null
  fi
  if [ $mode = stock ]; then
    export OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0
  fi
  python3 /opt/document-bench/bin/run_xlsx_helper_atomic.py enhance_workbook.py output/monthly_operations_report.xlsx >/dev/null 2>&1
  echo "$mode enhance rc=$?"
  cd /w
done
python3 - <<'PY'
import hashlib, zipfile
def digest(p):
    z = zipfile.ZipFile(p)
    names = sorted(z.namelist())
    members = {n: hashlib.md5(z.read(n)).hexdigest()[:10] for n in names}
    return members
a = digest("/w/enh_stock/output/monthly_operations_report.xlsx")
c = digest("/w/enh_combo/output/monthly_operations_report.xlsx")
assert a.keys() == c.keys(), "member lists differ"
diff = [k for k in a if a[k] != c[k]]
print("members:", len(a))
print("stock vs combo differing members:", diff)
import zipfile
if "docProps/core.xml" in diff:
    print("core.xml stock:", zipfile.ZipFile("/w/enh_stock/output/monthly_operations_report.xlsx").read("docProps/core.xml").decode()[:260].replace("\n"," "))
    print("core.xml combo:", zipfile.ZipFile("/w/enh_combo/output/monthly_operations_report.xlsx").read("docProps/core.xml").decode()[:260].replace("\n"," "))
PY
echo ENH-DONE
