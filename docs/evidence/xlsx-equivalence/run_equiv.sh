#!/bin/bash
# Equivalence evidence: stock vs speedups vs cache-HIT, on the combo image.
set -u
cd /w

echo "=== mode A: stock (both off), load fingerprint ==="
OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0 python3 fp.py A > fp_A.json 2>&1
echo "=== mode A: stock, save determinism control (two independent saves) ==="
OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0 python3 save.py /w/out_stock1.xlsx > save_A1.txt 2>&1
OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0 python3 save.py /w/out_stock2.xlsx > save_A2.txt 2>&1

echo "=== mode B: speedups only, load fingerprint ==="
OPENPYXL_CACHE=0 python3 fp.py B > fp_B.json 2>&1

echo "=== mode C: combo (both on), fresh cache ==="
rm -rf /tmp/oxlcache
python3 fp.py C_MISS > fp_C_miss.json 2>&1
python3 fp.py C_HIT > fp_C_hit.json 2>&1
python3 save.py /w/out_combo_hit.xlsx > save_C.txt 2>&1

echo "=== compare load fingerprints ==="
python3 - <<'PY'
import json
def load(t):
    for line in open("/w/"+t.split("/")[-1]):
        if line.startswith("FPRESULT "):
            return json.loads(line[9:])
A = load("fp_A.json"); B = load("fp_B.json"); Cm = load("fp_C_miss.json"); Ch = load("fp_C_hit.json")
print("A  stock      TOTAL:", A["TOTAL"])
print("B  speedups   TOTAL:", B["TOTAL"])
print("C  combo MISS TOTAL:", Cm["TOTAL"])
print("C  combo HIT  TOTAL:", Ch["TOTAL"])
print("A==B:", A["TOTAL"]==B["TOTAL"], " A==Cmiss:", A["TOTAL"]==Cm["TOTAL"], " A==Chit:", A["TOTAL"]==Ch["TOTAL"])
if A["TOTAL"] != Ch["TOTAL"]:
    for k in A["sheets"]:
        if A[k] != Ch[k]:
            print("DIFF sheet:", k, A[k], Ch[k])
    for k in ("defined_names","external_links","sheets"):
        if A[k] != Ch[k]: print("DIFF", k, A[k], Ch[k])
PY

echo "=== compare save content ==="
python3 - <<'PY'
def digest(t):
    d = None
    members = []
    for line in open("/w/"+t.split("/")[-1]):
        if line.startswith("SAVEDIGEST "):
            d = line.split()[2]
        elif line.startswith("  MEMBER "):
            members.append(line.strip()[9:])
    return d, members
dA1, mA1 = digest("save_A1.txt")
dA2, mA2 = digest("save_A2.txt")
dC, mC = digest("save_C.txt")
print("stock save #1 :", dA1)
print("stock save #2 :", dA2)
print("combo HIT save:", dC)
print("stock determinism control (A1==A2):", dA1 == dA2)
print("stock vs combo (A1==C):", dA1 == dC)
if dA1 != dC:
    s1 = set(mA1); s2 = set(mC)
    for m in sorted(s1 ^ s2): print("  MEMBER-DIFF", m)
PY
echo EVIDENCE-DONE
