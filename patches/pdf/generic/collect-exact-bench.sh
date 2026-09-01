#!/bin/bash
# exact-count run: create container with image $1, detect-mode bench, collect complete probe logs
set -u
IMG="$1"
CFG=~/yxy/document-bench/config/common/document-pdf.yaml
cd ~/yxy/document-bench
source venv/bin/activate
sed -i "s|image: \"[^\"]*\"|image: \"${IMG}\"|" "$CFG"
bench-core --provider docker --config "$CFG" --cleanup > /dev/null 2>&1
bench-core --provider docker --config "$CFG" --create-only -n 1 > /dev/null 2>&1
C=$(docker ps -q --filter name=doc-bench)
docker exec $C sh -c 'rm -f /tmp/zcount/*.log' 2>/dev/null
bench-core --provider docker --config "$CFG" --detect > /tmp/bench_last.log 2>&1
OUT=/tmp/zexact_${IMG//[:\/]/_}.txt
docker exec $C sh -c 'for f in /tmp/zcount/*.log; do [ -f "$f" ] && echo "==_$f" && cat "$f"; done' > "$OUT" 2>/dev/null
grep -E "^PDF-P0" /tmp/bench_last.log | awk '{print $1, $3}' | tr '\n' ' '
echo ""
grep -E "Success Rate" /tmp/bench_last.log | tail -1
bench-core --provider docker --config "$CFG" --cleanup > /dev/null 2>&1
echo "collected: $OUT ($(grep -c "^==_" $OUT) proc-logs)"
