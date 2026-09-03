#!/bin/bash
set -e
cd /tmp/pyout
FG=~/fg

# 0) clean (?) noise frames
python3 /tmp/clean.py b3.raw b7.raw
python3 /tmp/clean.py a.raw a5.raw

# 1) full flame graphs (detail preserved: line numbers + symbolized libz)
perl $FG/flamegraph.pl --width 1600 \
  --title "PDF workload (10x fill + 10x render) x3 — 优化前: 系统 zlib (py-spy 99Hz native, 2080 samples)" \
  b7.raw > flame-full-before.svg
perl $FG/flamegraph.pl --width 1600 \
  --title "PDF workload (10x fill + 10x render) x3 — 优化后: zlib-ng 2.2.4 NEON (py-spy 99Hz native, 1577 samples)" \
  a5.raw > flame-full-after.svg

# 2) cropped: PNG encode -> zlib path only
python3 /tmp/crop.py b7.raw png-b7.folded
python3 /tmp/crop.py a5.raw png-a5.folded
perl $FG/flamegraph.pl --width 1600 --countname samples \
  --title "PNG 编码 -> zlib 路径 (优化前: 系统 zlib, 符号剥离) — libz 948 samples 占 65.7%" \
  png-b7.folded > png-zlib-before.svg
perl $FG/flamegraph.pl --width 1600 --countname samples \
  --title "PNG 编码 -> zlib 路径 (优化后: zlib-ng) — libz 477 samples 占 52.6%, 内部函数可见" \
  png-a5.folded > png-zlib-after.svg

# 3) differential: normalize (zlib/libc collapse) + strip line numbers, then difffolded
python3 /tmp/normalize.py b7.raw b8.raw
python3 /tmp/normalize.py a5.raw a6.raw
sed "s/:[0-9]*)/)/g" b8.raw > b9.raw
sed "s/:[0-9]*)/)/g" a6.raw > a7.raw
perl $FG/difffolded.pl b9.raw a7.raw > diff.folded
perl $FG/flamegraph.pl --width 1600 --countname samples \
  --title "差分火焰图 (基线=系统 zlib 2080 samples, 对比=zlib-ng 1577 samples): 蓝=耗时减少(被优化), 红=耗时增加" \
  < diff.folded > flame-diff.svg

echo ===diff中zlib主行===
grep -E ";zlib [0-9]+ [0-9]+$" diff.folded | sort -t" " -k2 -rn | head -2
grep -B1 '<title>zlib (' flame-diff.svg | grep -oE 'fill="rgb\([0-9, ]+\)"' | head -1
ls -la *.svg

# 4) repair double-encoded Chinese titles (flamegraph.pl re-encodes --title)
python3 fix_title.py flame-full-before.svg flame-full-after.svg png-zlib-before.svg png-zlib-after.svg flame-diff.svg
