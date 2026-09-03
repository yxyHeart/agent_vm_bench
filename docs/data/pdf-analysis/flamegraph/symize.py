"""Symbolize py-spy raw output (v2).

Rules per raw-address frame (ASLR disabled: libz base=0xfffff7ed0000, libc base=0xfffff7cc0000):
- nearest defined FUNC with st_size > 0 and offset within [st_value, st_value+st_size) -> name+0xoff
- otherwise -> gap; consecutive gap frames collapse into one "内部函数(符号剥离)" frame
"""

import bisect
import re
import subprocess
import sys

SRC, DST = sys.argv[1], sys.argv[2]

LIBS = {
    "libz.so.1.3": ("/tmp/libz_stock.so", 0xFFFFF7ED0000, "libz内部(符号剥离)"),
    "libc.so.6": ("/tmp/libc_stock.so", 0xFFFFF7CC0000, "libc内部(符号剥离)"),
}


def load_funcs(path):
    out = subprocess.check_output(["readelf", "-sW", path]).decode()
    funcs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[3] == "FUNC" and parts[6] != "UND":
            try:
                val = int(parts[1], 16)
                size = int(parts[2])
            except ValueError:
                continue
            name = parts[7].split("@")[0]
            if val and name:
                funcs.append((val, size, name))
    funcs.sort()
    return [f[0] for f in funcs], funcs


TABLE = {}
for mod, (path, base, gapname) in LIBS.items():
    addrs, funcs = load_funcs(path)
    TABLE[mod] = (addrs, funcs, base, gapname)

FRAME_RE = re.compile(r"^0x([0-9a-f]+) \((libz\.so\.1\.3|libc\.so\.6)\)$")

with open(SRC) as f, open(DST, "w") as out:
    for line in f:
        line = line.rstrip("\n")
        if " (libz.so.1.3)" not in line and " (libc.so.6)" not in line:
            out.write(line + "\n")
            continue
        stack, _, count = line.rpartition(" ")
        frames = []
        for fr in stack.split(";"):
            m = FRAME_RE.match(fr)
            if not m:
                frames.append(fr)
                continue
            addr, mod = int(m.group(1), 16), m.group(2)
            addrs, funcs, base, gapname = TABLE[mod]
            off = addr - base
            label = gapname
            i = bisect.bisect_right(addrs, off) - 1
            if i >= 0:
                val, size, name = funcs[i]
                if off - val < size:
                    label = f"{name}+0x{off - val:x} ({mod})"
            if label == gapname and frames and frames[-1] == gapname:
                continue
            frames.append(label)
        out.write(";".join(frames) + " " + count + "\n")
print("done", DST)
