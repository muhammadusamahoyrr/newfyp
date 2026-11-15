"""BGE-M3 (dense, zero-shot) vs base e5 and the two fine-tuned e5 retrievers,
on every set, Hit@1 with McNemar exact p for BGE-M3 vs each."""
import json
from collections import defaultdict
from math import comb

M = json.load(open("fit_bgem3_result.json", encoding="utf-8"))
A = json.load(open("fit_reeval_result.json", encoding="utf-8"))
T = json.load(open("fit_thirdstyle_result.json", encoding="utf-8"))
G = json.load(open("fit_stylegrid_result.json", encoding="utf-8"))

def mc(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)

def line(label, idx, ranks):  # ranks: {name: list}
    h = {k: [1 if v[i] == 1 else 0 for i in idx] for k, v in ranks.items()}
    out = f"{label:<34} n={len(idx):>4} " + " ".join(f"{k}={100*sum(x)/len(idx):5.1f}" for k, x in h.items())
    for k in ranks:
        if k == "bgem3":
            continue
        b = sum(1 for x, y in zip(h[k], h["bgem3"]) if not x and y); c = sum(1 for x, y in zip(h[k], h["bgem3"]) if x and not y)
        out += f" | bge-{k}: {100*(b-c)/len(idx):+5.1f} p={mc(b,c):.2g}"
    print(out)

for s in ("citation_1191", "legaluqa_128", "legaluqa_121"):
    r = {"e5": A["ranks"]["base"][s], "general": A["ranks"]["general"][s], "const": A["ranks"]["constitutional"][s], "bgem3": M["ranks"][s]}
    line(s, list(range(len(r["e5"]))), r)
rows = A["rows"]["citation_1191"]
r = {"e5": A["ranks"]["base"]["citation_1191"], "general": A["ranks"]["general"]["citation_1191"], "bgem3": M["ranks"]["citation_1191"]}
for u in (True, False):
    line(f"citation_1191 urdu={u}", [i for i, x in enumerate(rows) if x["urdu"] == u], r)
tr = T["rows"]["thirdstyle"]
r = {"e5": T["ranks"]["base"]["thirdstyle"], "general": T["ranks"]["general"]["thirdstyle"], "bgem3": M["ranks"]["thirdstyle"]}
line("thirdstyle clean-for-general", [i for i, x in enumerate(tr) if not x["leak_general"]], r)
cells = defaultdict(list)
for i, x in enumerate(G["rows"]):
    cells[(x["content"], x["style"])].append(i)
for content, model in (("uqa128", "general"), ("dev23", "general"), ("uqa121", "constitutional")):
    for st in ("original", "urdu", "layperson_en", "roman_urdu", "keyword"):
        idx = cells.get((content, st), [])
        r = {"e5": G["ranks"]["base"]["stylegrid"], model[:7]: G["ranks"][model]["stylegrid"], "bgem3": M["ranks"]["stylegrid"]}
        line(f"grid {content}/{st}", idx, r)
print(M["model"])
