import sys

src, dst = sys.argv[1], sys.argv[2]
out = {}
for line in open(src):
    stack, _, c = line.rstrip().rpartition(" ")
    frames = stack.split(";")
    for i, fr in enumerate(frames):
        if fr.startswith("save (PIL/Image.py"):
            key = ";".join(frames[i:])
            out[key] = out.get(key, 0) + int(c)
            break
with open(dst, "w") as f:
    for k, v in out.items():
        f.write(f"{k} {v}\n")
print(dst, "cropped stacks:", len(out), "samples:", sum(out.values()))
