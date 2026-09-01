#!/bin/bash
# Build the openpyxl_speedups extension for the py312k (self-built CPython)
# containers. Runs on the aarch64 build host; needs Cython (any host python)
# and the pyroot headers from patches/py312k/build-b2l.sh.
set -e
HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
GEN=${GEN_ROOT:-$HERE/../../build-gen}
CYTHON=${CYTHON:-cython}          # e.g. venv/bin/cython
PYINC=$GEN/pyroot/include/python3.12

"$CYTHON" "$HERE/openpyxl_speedups.pyx"
gcc -O3 -mcpu=tsv110 -fPIC -shared -I"$PYINC" \
    "$HERE/openpyxl_speedups.c" \
    -o "$HERE/openpyxl_speedups.cpython-312-aarch64-linux-gnu.so"

# image layer: gen-b3 = gen-b2l (PGO/LTO python + lxml writer) + speedups
docker build -t ubuntu-document-bench:gen-b3 "$HERE"
