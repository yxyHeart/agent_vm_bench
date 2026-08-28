#!/bin/bash
# Adapted from ~/yxy/grep-bench/scripts/perf-rg.sh for XLSX openpyxl full-load profiling.
# Profiles ONE representative heavy op: openpyxl load_workbook(template, read_only=False)
# (~24s, materializes the 123.5MB Raw_Sample sheet — the dominant XLSX cost).
set -uo pipefail
ROOT="${XLSX_BENCH_ROOT:-$HOME/yxy/document-bench}"
PY="${PY:-$ROOT/venv/bin/python}"
TPL="${TPL:-/tmp/xlsx_template.xlsx}"
OUT="$ROOT/results/perf"
mkdir -p "$OUT"
PREFIX="${PREFIX:-$OUT/xlsx-openpyxl-fullload}"

CMD=( "$PY" -c "from openpyxl import load_workbook; wb=load_workbook('$TPL', read_only=False); wb.close()" )

{
  echo "PY=$PY"
  echo "openpyxl=$($PY -c 'import openpyxl; print(openpyxl.__version__)')"
  echo "TPL=$TPL ($(stat -c%s "$TPL") bytes)"
  echo "mode=read_only=False (full materialization)"
  date
} > "$PREFIX.meta.txt"

echo "=== perf stat (PMU, single) ==="
perf stat \
  -e cycles,instructions,cache-references,cache-misses,branch-instructions,branch-misses,\
armv8_pmuv3_0/L1-dcache-loads/,armv8_pmuv3_0/L1-dcache-load-misses/,\
armv8_pmuv3_0/L1-icache-loads/,armv8_pmuv3_0/L1-icache-load-misses/,\
armv8_pmuv3_0/dTLB-loads/,armv8_pmuv3_0/dTLB-load-misses/,\
armv8_pmuv3_0/iTLB-loads/,armv8_pmuv3_0/iTLB-load-misses/ \
  -- "${CMD[@]}" > /dev/null 2> "$PREFIX.stat.txt" || true
if ! grep -qi "cycles" "$PREFIX.stat.txt"; then
  echo "(armv8 PMU events unavailable -> core set)"
  perf stat \
    -e cycles,instructions,cache-references,cache-misses,branch-instructions,branch-misses \
    -- "${CMD[@]}" > /dev/null 2> "$PREFIX.stat.txt" || true
fi
cat "$PREFIX.stat.txt"

echo ""
echo "=== perf record (call-graph dwarf, single) ==="
perf record -F 997 -g --call-graph dwarf -o "$PREFIX.perf.data" -- "${CMD[@]}" > /dev/null 2>&1 || true
perf script -i "$PREFIX.perf.data" > "$PREFIX.perf-script.txt" 2>/dev/null || true
echo "=== Top hotspots ==="
perf report -i "$PREFIX.perf.data" --stdio --no-children -g none > "$PREFIX.report.txt" 2>/dev/null || true
head -50 "$PREFIX.report.txt"

echo ""
echo "=== strace -c -f ==="
strace -c -f -o "$PREFIX.strace.txt" -- "${CMD[@]}" > /dev/null 2>&1 || true
cat "$PREFIX.strace.txt"
