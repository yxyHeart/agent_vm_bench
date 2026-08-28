#!/usr/bin/env python3
"""Generate py-spy flamegraphs for each XLSX recipe tool call step."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RECIPE = "/tmp/xlsx_key_operations.json"
WS = "/root/.openclaw/workspace/tool-modeling/SUB-MEM-OFFICE-01"
FLAMES = Path("/tmp/flames")


def install_pyspy():
    try:
        subprocess.run(["py-spy", "--version"], capture_output=True, check=True)
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "py-spy"], check=True)


def extract_cwd(cmd):
    m = re.match(r'cd\s+("?\S+"?)\s+&&\s+', cmd)
    if m:
        return m.group(1).strip('"')
    return WS


def extract_code_dash_c(cmd):
    """Extract Python code from python3 -c "..." handling escaped quotes."""
    marker = 'python3 -c "'
    idx = cmd.find(marker)
    if idx == -1:
        marker = "python3 -c '"
        idx = cmd.find(marker)
        if idx == -1:
            return None
        quote = "'"
    else:
        quote = '"'
    start = idx + len(marker)
    i = start
    while i < len(cmd):
        if cmd[i] == '\\':
            i += 2
        elif cmd[i] == quote:
            return cmd[start:i]
        else:
            i += 1
    return cmd[start:]


def extract_code_heredoc(cmd):
    m = re.search(r"<<\s*'PYEOF'\n(.*?)\nPYEOF", cmd, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'<<\s*PYEOF\n(.*?)\nPYEOF', cmd, re.DOTALL)
    if m:
        return m.group(1)
    return None


def strip_trailing(cmd):
    """Remove output redirection and pipes from command tail."""
    cmd = re.sub(r'\s*2>&1\s*\|\s*head\s+-\d+\s*$', '', cmd)
    cmd = re.sub(r'\s*>\s*\S+\s*2>&1\s*$', '', cmd)
    cmd = re.sub(r'\s*\|\s*head\s+-\d+\s*$', '', cmd)
    cmd = re.sub(r'\s*2>&1\s*$', '', cmd)
    return cmd.strip()


def extract_redirect(cmd):
    """Extract output file from > file 2>&1 pattern."""
    m = re.search(r'>\s*(\S+)\s*2>&1', cmd)
    if m:
        return m.group(1)
    return None


def run_pyspy(svg_path, cwd, python_cmd, redirect_file=None):
    """Run py-spy record on a python3 command."""
    if redirect_file:
        full = f"cd {cwd} && py-spy record -o {svg_path} --duration 300 -- {python_cmd} > {redirect_file} 2>/dev/null"
    else:
        full = f"cd {cwd} && py-spy record -o {svg_path} --duration 300 -- {python_cmd}"
    print(f"  py-spy: {full[:120]}...")
    r = subprocess.run(full, shell=True)
    sz = svg_path.stat().st_size if svg_path.exists() else 0
    print(f"  exit={r.returncode}, svg={svg_path.name} ({sz} bytes)")


def run_step(step_num, phase_id, idx, fn, args):
    short_phase = phase_id.replace("XLSX-", "").split("-")[0]
    name = f"{short_phase}-{idx:02d}_{fn}"
    svg_path = FLAMES / f"step{step_num:02d}_{name}.svg"

    print(f"\n{'='*60}")
    print(f"Step {step_num}/15: {phase_id} [{idx}] {fn}")
    print(f"{'='*60}")

    if fn == "read":
        path = args["path"]
        subprocess.run(f"test -f {path} && head -c 65536 {path} >/dev/null", shell=True)
        print(f"  non-Python (file check), no flamegraph")
        return

    if fn == "write":
        path = args["path"]
        content = args["content"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        print(f"  file write ({len(content)} bytes), no flamegraph")
        return

    cmd = args["command"].replace("__DOCUMENT_RECALC_TIMEOUT__", "180")
    cwd = extract_cwd(cmd)

    if "python3" not in cmd:
        subprocess.run(cmd, shell=True)
        print(f"  non-Python exec, no flamegraph")
        return

    redirect_file = extract_redirect(cmd)
    redirect_file = os.path.join(cwd, redirect_file) if redirect_file else None

    code = extract_code_heredoc(cmd)
    if code:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(code)
            temp_py = f.name
        run_pyspy(svg_path, cwd, f"python3 {temp_py}", None)
        return

    code = extract_code_dash_c(cmd)
    if code:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(code)
            temp_py = f.name
        run_pyspy(svg_path, cwd, f"python3 {temp_py}", None)
        return

    m = re.search(r'python3\s+(\S+\.py)\s*(.*)', cmd)
    if m:
        script = m.group(1)
        sargs = strip_trailing(m.group(2))
        python_cmd = f"python3 {script}"
        if sargs:
            python_cmd += f" {sargs}"
        run_pyspy(svg_path, cwd, python_cmd, redirect_file)
        return

    subprocess.run(cmd, shell=True)
    print(f"  could not parse python3, ran without py-spy")


def main():
    install_pyspy()
    FLAMES.mkdir(exist_ok=True)

    with open(RECIPE) as f:
        recipe = json.load(f)

    subprocess.run(f"mkdir -p /root/.openclaw/workspace/tool-modeling && rm -rf {WS} && cp -a /opt/document-bench/xlsx {WS}", shell=True, check=True)
    subprocess.run(f"mkdir -p {WS}/output", shell=True, check=True)

    step_num = 0
    for phase in recipe["key_operations"]:
        phase_id = phase["operation_id"]
        for idx, source_call in enumerate(phase["source_tool_calls"]):
            step_num += 1
            call = source_call["tool_call"]
            run_step(step_num, phase_id, idx, call["function_name"], call["arguments"])

    print(f"\n{'='*60}")
    print(f"Done! {step_num} steps executed.")
    print(f"Flamegraphs in: {FLAMES}")
    svgs = sorted(FLAMES.glob("*.svg"))
    for svg in svgs:
        print(f"  {svg.name} ({svg.stat().st_size:,} bytes)")
    print(f"Total: {len(svgs)} flamegraphs")


if __name__ == "__main__":
    main()
