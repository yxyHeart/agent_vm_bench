import re
import sys

src, dst = sys.argv[1], sys.argv[2]


def is_libz(fr):
    return "(libz.so" in fr or fr.startswith("libz内部")


def is_libc(fr):
    return "(libc.so" in fr or fr.startswith("libc内部")


with open(src) as f, open(dst, "w") as out:
    for line in f:
        stack, _, c = line.rstrip().rpartition(" ")
        frames = []
        for fr in stack.split(";"):
            if is_libz(fr):
                if not frames or frames[-1] != "zlib":
                    frames.append("zlib")
            elif is_libc(fr):
                if not frames or frames[-1] != "libc内部":
                    frames.append("libc内部")
            elif ".py:" in fr or fr.endswith(".py)"):
                frames.append(fr)
        out.write(";".join(frames) + " " + c + "\n")
print(dst, "ok")
