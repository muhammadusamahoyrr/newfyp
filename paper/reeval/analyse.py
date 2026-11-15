import json, math, random, sys
from math import comb

R = json.load(open(sys.argv[1], encoding="utf-8"))
rk, rows = R["ranks"], R["rows"]


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def hit1(v):
    return [1 if x == 1 else 0 for x in v]


def mrr(v):
    return sum(1 / x for x in v if x) / len(v)


def ndcg5(v, ng):
    tot = 0
    for x, g in zip(v, ng):
        idcg = sum(1 / math.log2(i + 1) for i in range(1, min(g, 5) + 1))
        tot += (1 / math.log2(x + 1) / idcg) if (x and x <= 5) else 0
    return tot / len(v)


def boot(a, b, n=10000, seed=1):
    rnd = random.Random(seed); m = len(a); d = []
    for _ in range(n):
        idx = [rnd.randrange(m) for _ in range(m)]
        d.append(sum(b[i] - a[i] for i in idx) / m)
    d.sort()
    return d[int(0.025 * n)], d[int(0.975 * n)]


def compare(setname, model, mask=None, label=None):
    base, ft = rk["base"][setname], rk[model][setname]
    ng = [r["ngold"] for r in rows[setname]]
    idx = [i for i in range(len(base)) if (mask is None or mask[i])]
    b0 = [hit1(base)[i] for i in idx]; f0 = [hit1(ft)[i] for i in idx]
    bb = sum(1 for x, y in zip(b0, f0) if x == 0 and y == 1)
    cc = sum(1 for x, y in zip(b0, f0) if x == 1 and y == 0)
    lo, hi = boot(b0, f0)
    bs = [base[i] for i in idx]; fs = [ft[i] for i in idx]; g = [ng[i] for i in idx]
    print(f"{label or setname:<34} {model:<15} n={len(idx):>4}  Hit@1 {sum(b0)/len(idx):.3f}->{sum(f0)/len(idx):.3f} "
          f"d={100*(sum(f0)-sum(b0))/len(idx):+5.1f}pt CI[{100*lo:+.1f},{100*hi:+.1f}]  "
          f"b(0->1)={bb} c(1->0)={cc} p={mcnemar(bb, cc):.2g}  "
          f"MRR {mrr(bs):.3f}->{mrr(fs):.3f}  nDCG5 {ndcg5(bs, g):.3f}->{ndcg5(fs, g):.3f}")


for s in ("citation_1191", "legaluqa_128", "legaluqa_121"):
    for m in ("general", "constitutional"):
        compare(s, m)
print()
dom = [r["domain"] for r in rows["citation_1191"]]
for d in sorted(set(dom)):
    for m in ("general", "constitutional"):
        compare("citation_1191", m, [x == d for x in dom], f"citation_1191[{d}]")
urdu = [r["urdu"] for r in rows["citation_1191"]]
for u in (True, False):
    compare("citation_1191", "general", [x == u for x in urdu], f"citation_1191[urdu={u}]")
leak = R["leak_general_121"]
print()
for lk in (True, False):
    for m in ("general", "constitutional"):
        compare("legaluqa_121", m, [x == lk for x in leak], f"legaluqa_121[leak_general={lk}]")
print("\nleak counts 121:", sum(leak), "/", len(leak), " 128:", sum(R["leak_general_128"]))


def rank_changes(setname, model):
    MISS = 10_000
    base, ft = rk["base"][setname], rk[model][setname]
    imp = sum(1 for x, y in zip(base, ft) if (y or MISS) < (x or MISS))
    wor = sum(1 for x, y in zip(base, ft) if (y or MISS) > (x or MISS))
    return imp, wor, len(base) - imp - wor
print("rank-change counts general 1191:", rank_changes("citation_1191", "general"),
      " general 128:", rank_changes("legaluqa_128", "general"),
      " const 1191:", rank_changes("citation_1191", "constitutional"))

for k, thr in (("nd_citation_test_vs_general_train", (0.95, 0.97)), ("nd_121_vs_constitutional_train", (0.95, 0.97)),
               ("nd_128_vs_general_train", (0.95, 0.97))):
    v = R[k]
    print(k, "n", len(v), "max", round(max(v), 3), "median", round(sorted(v)[len(v)//2], 3),
          " >=.95:", sum(x >= .95 for x in v), " >=.97:", sum(x >= .97 for x in v))
print("exact dup:", R["exact_dup_citation_test_in_train"])
nd = R["nd_citation_test_vs_general_train"]
compare("citation_1191", "general", [x < 0.95 for x in nd], "citation_1191[maxcos<0.95]")
compare("citation_1191", "general", [x < 0.90 for x in nd], "citation_1191[maxcos<0.90]")
print(R["verified"])
