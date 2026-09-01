#!/bin/bash
# Build the openpyxl_speedups extension and the speedups image layer.
# Runs on the aarch64 build host against the DISTRO CPython 3.12 (the image
# keeps the stock interpreter; only this extension is added).
#
# Needs: cython on PATH (any host python), python3.12 headers (PYINC below),
# and the base image ubuntu-document-bench:24.04-linuxarm64 locally.
set -e
HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
CYTHON=${CYTHON:-cython}
# headers for the *distro* 3.12 (any 3.12 CPython headers work; the .so only
# links against libpython ABI 3.12 which the image already ships)
PYINC=${PYINC:-$HERE/../../../build-gen/pyroot/include/python3.12}

# 1. pyx -> C
"$CYTHON" "$HERE/openpyxl_speedups.pyx"

# 2. C -> native extension
gcc -O3 -fPIC -shared -I"$PYINC" \
    "$HERE/openpyxl_speedups.c" \
    -o "$HERE/openpyxl_speedups.cpython-312-aarch64-linux-gnu.so"

# 3. image layer: distro base + the three injection files
docker build -t ubuntu-document-bench:speedups "$HERE"
