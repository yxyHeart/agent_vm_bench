import zlib

with open("/proc/self/maps") as f:
    l = [x for x in f if "libz.so" in x][0].split()[-1]
assert "/opt/zlib/" in l, l
zlib.compress(b"x" * 100)
print("probe OK:", l)
