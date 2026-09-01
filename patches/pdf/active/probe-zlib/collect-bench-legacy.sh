#!/bin/bash
# run one bench (3 rounds x 1 container) on $1 image, collect zcount probe logs to /tmp/zcol_$1.txt
set -u
IMG="$1"
CFG=~/yxy/document-bench/config/common/document-pdf.yaml
cd ~/yxy/document-bench
source venv/bin/activate
sed -i "s|image: \"[^\"]*\"|image: \"${IMG}\"|" "$CFG"
OUT=/tmp/zcol_${IMG//[:\/]/_}.txt
rm -f "$OUT"
bench-core --provider docker --config "$CFG" > /tmp/bench_last.log 2>&1 &
BPID=$!
while kill -0 $BPID 2>/dev/null; do
    for c in $(docker ps -q); do
        docker exec $c sh -c 'for f in /tmp/zcount/*.log; do [ -f "$f" ] && echo "==_$f" && cat "$f"; done' 2>/dev/null
    done >> "$OUT"
    sleep 2
done
wait $BPID
echo "=== bench done: $IMG ==="
grep -E "^PDF-P0|Success Rate" /tmp/bench_last.log | tail -5
