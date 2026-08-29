#!/usr/bin/env python3
"""Redo broken flamegraph steps: 7 (subprocesses), 13, 14. Regenerate clean recalc JSON."""
import subprocess
from pathlib import Path

WS = "/root/.openclaw/workspace/tool-modeling/SUB-MEM-OFFICE-01"
FLAMES = Path("/tmp/flames")


def run(cmd):
    r = subprocess.run(cmd, shell=True, cwd=WS)
    return r.returncode


run("cp input/monthly_operations_template.xlsx output/monthly_operations_report.xlsx")
print("[1/5] workbook reset from template")

svg7 = FLAMES / "step07_P02-01_exec.svg"
run(
    f"py-spy record -o {svg7} --duration 300 --subprocesses -- "
    "python3 /opt/document-bench/bin/run_xlsx_helper_atomic.py "
    "enhance_workbook.py output/monthly_operations_report.xlsx"
)
print(f"[2/5] step07 redone with --subprocesses: {svg7.stat().st_size:,} bytes")

run(
    "python3 /root/.openclaw/skills/xlsx/scripts/recalc.py output/monthly_operations_report.xlsx 180 "
    "> output/formula_recalc.json 2>&1"
)
r = subprocess.run(
    "python3 -c \"import json; print('recalc:', json.load(open('output/formula_recalc.json'))['status'])\"",
    shell=True, cwd=WS, capture_output=True, text=True,
)
print(f"[3/5] recalc redone WITHOUT py-spy: {r.stdout.strip()}")

svg13 = FLAMES / "step13_P04-00_exec.svg"
run(
    f"py-spy record -o {svg13} --duration 300 -- "
    "python3 input/verify_xlsx_enhanced.py output/monthly_operations_report.xlsx output/formula_recalc.json "
    "output/business_verification.json output/monthly_operations_summary.csv output/reconciliation_summary.csv"
)
print(f"[4/5] step13 redone: {svg13.stat().st_size:,} bytes")

svg14 = FLAMES / "step14_P04-01_exec.svg"
run(
    f"py-spy record -o {svg14} --duration 300 -- "
    "python3 /opt/document-bench/bin/write_xlsx_summary.py output/monthly_operations_report.xlsx "
    "output/business_verification.json output/formula_recalc.json output/xlsx_enhancement_summary.json "
    "output/monthly_operations_summary.csv output/reconciliation_summary.csv"
)
print(f"[5/5] step14 redone: {svg14.stat().st_size:,} bytes")

r = subprocess.run(
    "python3 -c \"import json; v=json.load(open('output/business_verification.json')); "
    "print('business_verification:', v['status'], v['failures'])\"",
    shell=True, cwd=WS, capture_output=True, text=True,
)
print(r.stdout.strip())
