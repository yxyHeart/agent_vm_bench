from pypdf import PdfReader, PdfWriter

import pypdf.generic._base as b

print("metaclass:", type(b.PdfObject).__name__)
r = PdfReader("/opt/document-bench/pdf/input/of306_aug2023.pdf")
w = PdfWriter(clone_from=r)
print("patched pypdf reads OK, pages=", len(r.pages))
