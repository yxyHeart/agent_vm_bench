def load(t):
    d, members = None, []
    for line in open(t):
        if line.startswith("SAVEDIGEST "):
            d = line.split()[2]
        elif line.startswith("  MEMBER "):
            members.append(line.strip()[9:])
    return d, members

dA1, mA1 = load("/w/save_A1.txt")
dA2, mA2 = load("/w/save_A2.txt")
dC,  mC  = load("/w/save_C.txt")

def diff(a, b):
    s1, s2 = dict(x.rsplit(":",1) for x in a), dict(x.rsplit(":",1) for x in b)
    assert s1.keys() == s2.keys(), (sorted(s1), sorted(s2))
    return {k for k in s1 if s1[k] != s2[k]}, s1, s2

d12, _, _ = diff(mA1, mA2)
d1C, _, _ = diff(mA1, mC)
print("member count:", len(mA1), len(mA2), len(mC))
print("A1 vs A2 (stock vs stock) differing members:", sorted(d12))
print("A1 vs C  (stock vs combo) differing members:", sorted(d1C))
allm = set(mA1)
print("total members:", len(allm))
