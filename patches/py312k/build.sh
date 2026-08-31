#!/bin/bash
# Build a Kunpeng-tuned CPython 3.12.3 for the document-bench containers.
# Runs on the aarch64 build host (no root needed): gcc + make + extracted
# zlib/openssl -devel headers under ../rpmroot (see report for the
# dnf download + rpm2cpio step).
#
# Tuning: -O3 -mcpu=tsv110 (CPU part 0xd02; gcc has no tsv120, nearest
# neighbour), computed gotos, LTO, and PGO trained on an openpyxl workload
# corpus (../corpus.py) instead of the default test suite.
set -e
ROOT=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
GEN=${GEN_ROOT:-$ROOT/../build-gen}
mkdir -p "$GEN"
cd "$GEN"
[ -d Python-3.12.3 ] || { curl -sLO https://www.python.org/ftp/python/3.12.3/Python-3.12.3.tgz && tar xf Python-3.12.3.tgz; }
cp "$ROOT/py312k/corpus.py" .
cd Python-3.12.3
make distclean > /dev/null 2>&1 || true
./configure --prefix="$GEN/pyroot" --with-computed-gotos --without-ensurepip --with-lto \
  CPPFLAGS="-I$GEN/rpmroot/usr/include" LDFLAGS="-L$GEN/rpmroot/usr/lib64" \
  CFLAGS="-O3 -mcpu=tsv110" > "$GEN/configure.log" 2>&1
make -j"$(nproc)" PROFILE_TASK="$GEN/corpus.py" profile-opt > "$GEN/build.log" 2>&1
make install > "$GEN/install.log" 2>&1
"$GEN/pyroot/bin/python3" -V
