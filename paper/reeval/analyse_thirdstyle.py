"""Third question style: Hit@1 / MRR@10, bootstrap CI, McNemar exact, on the
subset whose gold passages are clean for each model (no training positive)."""
import json, random, sys
from math import comb

R = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "fit_thirdstyle_result.json", encoding="utf-8"))
rows = R["rows"]["thirdstyle"]; rk = R["ranks"]


def mc(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def boot(a, f, n=10000, seed=1):
    rnd = random.Random(seed); m = len(a); d = []
    for _ in range(n):
        idx = [rnd.randrange(m) for _ in range(m)]
        d.append(sum(f[i] - a[i] for i in idx) / m)
    d.sort(); return d[int(.025 * n)], d[int(.975 * n)]


def report(model, mask, label):
    idx = [i for i, ok in enumerate(mask) if ok]
    b = [1 if rk["base"]["thirdstyle"][i] == 1 else 0 for i in idx]
    f = [1 if rk[model]["thirdstyle"][i] == 1 else 0 for i in idx]
    bb = sum(1 for x, y in zip(b, f) if not x and y); cc = sum(1 for x, y in zip(b, f) if x and not y)
    lo, hi = boot(b, f)
    mrr = lambda m: sum(1 / rk[m]["thirdstyle"][i] for i in idx if rk[m]["thirdstyle"][i]) / len(idx)
    print(f"{label:<44}{model:<15} n={len(idx):>3} Hit@1 {sum(b)/len(idx):.3f}->{sum(f)/len(idx):.3f} "
          f"d={100*(sum(f)-sum(b))/len(idx):+5.1f} CI[{100*lo:+.1f},{100*hi:+.1f}] b={bb} c={cc} p={mc(bb,cc):.2g} "
          f"MRR {mrr('base'):.3f}->{mrr(model):.3f}")


allm = [True] * len(rows)
for m in ("general", "constitutional"):
    report(m, [not r[f"leak_{m}"] for r in rows], "clean for this model")
    report(m, allm, "all 60 (incl. leaked gold)")
report("general", [r["leak_general"] for r in rows], "leaked only (gold = training positive)")
report("general", [not r["leak_general"] and r["lang"] == "en" for r in rows], "clean, English only")
report("general", [not r["leak_general"] and r["lang"] != "en" for r in rows], "clean, non-English")
report("constitutional", [not r["leak_constitutional"] and r["domain"] == "constitutional" for r in rows], "clean, constitutional domain")
nd = R["nd_third_vs_general_train"]
print("near-dup vs general train: max", round(max(nd), 3), " >=.95:", sum(x >= .95 for x in nd))
print("clean-for-general domains:", {d: sum(1 for r in rows if not r['leak_general'] and r['domain'] == d) for d in set(r['domain'] for r in rows)})
print("clean-for-general languages:", {d: sum(1 for r in rows if not r['leak_general'] and r['lang'] == d) for d in set(r['lang'] for r in rows)})
print(R["verified"])
