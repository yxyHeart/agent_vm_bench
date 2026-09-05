import hashlib
import sys
import zipfile

from openpyxl import load_workbook

SRC = "/opt/document-bench/xlsx/input/monthly_operations_template.xlsx"


def zip_content_digest(p):
    z = zipfile.ZipFile(p)
    names = sorted(z.namelist())
    h = hashlib.sha256()
    members = []
    for n in names:
        d = z.read(n)
        h.update(n.encode())
        h.update(d)
        members.append(f"{n}:{hashlib.md5(d).hexdigest()[:8]}")
    return h.hexdigest(), members


if __name__ == "__main__":
    out = sys.argv[1]
    wb = load_workbook(SRC, data_only=False)
    wb.save(out)
    wb.close()
    dg, members = zip_content_digest(out)
    print("SAVEDIGEST " + out + " " + dg)
    for m in members:
        print("  MEMBER " + m)
