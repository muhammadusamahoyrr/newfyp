"""Style grid: Hit@1 per (content set, style) for base and each fine-tuned
model, with bootstrap CI of the gain and McNemar exact p."""
import json, random, sys
from collections import defaultdict
from math import comb

R = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "fit_stylegrid_result.json", encoding="utf-8"))
rows, rk = R["rows"], R["ranks"]

def mc(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)

def boot(a, f, n=5000, seed=1):
    rnd = random.Random(seed); m = len(a); d = []
    for _ in range(n):
        idx = [rnd.randrange(m) for _ in range(m)]
        d.append(sum(f[i] - a[i] for i in idx) / m)
    d.sort(); return d[int(.025 * n)], d[int(.975 * n)]

MODEL_FOR = {"uqa128": "general", "dev23": "general", "uqa121": "constitutional"}
cells = defaultdict(list)
for i, r in enumerate(rows):
    cells[(r["content"], r["style"])].append(i)
ORDER = ["original", "urdu", "layperson_en", "roman_urdu", "keyword"]
for content in ("uqa128", "dev23", "uqa121"):
    for model in (MODEL_FOR[content], "general" if MODEL_FOR[content] == "constitutional" else "constitutional"):
        clean = model == MODEL_FOR[content]
        print(f"\n== content {content}  model {model}{'' if clean else '  (NOT clean for this model)'}")
        for st in ORDER:
            idx = cells.get((content, st), [])
            if not idx:
                continue
            b = [1 if rk["base"]["stylegrid"][i] == 1 else 0 for i in idx]
            f = [1 if rk[model]["stylegrid"][i] == 1 else 0 for i in idx]
            bb = sum(1 for x, y in zip(b, f) if not x and y); cc = sum(1 for x, y in zip(b, f) if x and not y)
            lo, hi = boot(b, f)
            print(f"  {st:<13} n={len(idx):>3}  base {100*sum(b)/len(idx):5.1f}  {model[:5]} {100*sum(f)/len(idx):5.1f}  "
                  f"d={100*(sum(f)-sum(b))/len(idx):+5.1f} CI[{100*lo:+.1f},{100*hi:+.1f}]  b={bb:>3} c={cc:>3} p={mc(bb,cc):.2g}")
print(R["verified"])
