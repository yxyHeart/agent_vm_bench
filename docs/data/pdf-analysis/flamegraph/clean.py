import re
import sys

src, dst = sys.argv[1], sys.argv[2]
DROP = re.compile(r"^0x[0-9a-f]+ \(\?\)$")

with open(src) as f, open(dst, "w") as out:
    for line in f:
        stack, _, c = line.rstrip().rpartition(" ")
        frames = [fr for fr in stack.split(";") if not DROP.match(fr)]
        out.write(";".join(frames) + " " + c + "\n")
print(dst, "cleaned")
