#!/bin/bash
set -e
cd /usr/local/lib/python3.12/dist-packages/pypdf
sed -i "s/^class PdfObject(PdfObjectProtocol):/class PdfObject:/" generic/_base.py
sed -i "s/^class XmpInformation(XmpInformationProtocol, PdfObject):/class XmpInformation(PdfObject):/" xmp.py
rm -rf __pycache__ generic/__pycache__
cd /
python3 - <<'PYEOF'
import pypdf.generic._base as b
assert type(b.PdfObject).__name__ == "type", "protocol patch failed"
from pypdf import PdfReader
r = PdfReader("/opt/document-bench/pdf/input/of306_aug2023.pdf")
assert len(r.pages) == 3
print("pypdf protocol-patch OK")
PYEOF
export LD_PRELOAD=/opt/zlib-ng/lib/libz.so.1
python3 - <<'PYEOF'
with open("/proc/self/maps") as f:
    libs = sorted({l.split()[-1] for l in f if "libz.so" in l})
assert any("zlib-ng" in l or "opt" in l for l in libs), libs
print("zlib-ng via LD_PRELOAD OK:", libs)
PYEOF
