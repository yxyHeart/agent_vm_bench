"""Repair double-encoded (UTF-8 -> Latin-1 -> UTF-8) titles in flamegraph.pl SVGs.

flamegraph.pl re-encodes the --title string (raw UTF-8 bytes get treated as Latin-1
and re-emitted as UTF-8), producing mojibake like "ç¼ç". The transform is reversible:
mojibake.encode('latin-1').decode('utf-8') == original.

Usage: python3 fix_title.py file1.svg [file2.svg ...]
"""
import re
import sys

TITLE_RE = re.compile(r'(<text id="title"[^>]*>)([^<]*)(</text>)')


def repair(text):
    if text.isascii():
        return None
    try:
        fixed = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return fixed if fixed != text else None


for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        src = f.read()

    def sub(m):
        fixed = repair(m.group(2))
        return m.group(1) + (fixed if fixed else m.group(2)) + m.group(3)

    dst = TITLE_RE.sub(sub, src)
    if dst != src:
        with open(path, "w", encoding="utf-8") as f:
            f.write(dst)
        print(f"fixed: {path}")
    else:
        print(f"unchanged: {path}")
