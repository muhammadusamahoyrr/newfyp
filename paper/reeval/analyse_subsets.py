import json, sys

R = json.load(open(sys.argv[1], encoding="utf-8"))
cross = json.load(open("crossstyle_test.json", encoding="utf-8"))
tq = json.load(open("finetune/test_questions.json", encoding="utf-8"))
tt = json.load(open("finetune/train_triplets.json", encoding="utf-8"))
test_q = {t["question"].strip() for t in tq}
train_q = {r["query"].removeprefix("query: ").strip() for r in tt}
in_test = [t["question"].strip() in test_q for t in cross]
in_train = [t["question"].strip() in train_q for t in cross]
print("128-set: in const TEST", sum(in_test), " in const TRAIN", sum(in_train), " neither", sum(1 for a, b in zip(in_test, in_train) if not a and not b))
from math import comb
def p(b, c):
    n=b+c; k=min(b,c); return min(1,2*sum(comb(n,i) for i in range(k+1))/2**n) if n else 1
def cmp(name, model, mask, label):
    base, ft = R["ranks"]["base"][name], R["ranks"][model][name]
    idx=[i for i,m in enumerate(mask) if m]; b=[base[i]==1 for i in idx]; f=[ft[i]==1 for i in idx]
    bb=sum(1 for x,y in zip(b,f) if not x and y); cc=sum(1 for x,y in zip(b,f) if x and not y)
    print(f"{label:<44}{model:<15} n={len(idx):>4} Hit@1 {sum(b)/len(idx):.3f}->{sum(f)/len(idx):.3f} d={100*(sum(f)-sum(b))/len(idx):+5.1f} b={bb} c={cc} p={p(bb,cc):.2g}")
rows = R["rows"]["citation_1191"]
cmp("legaluqa_128","constitutional",in_train,"128 & in const TRAIN")
cmp("legaluqa_128","constitutional",[not x for x in in_train],"128 & NOT in const train")
cmp("legaluqa_128","general",in_train,"128 & in const TRAIN")
for m in ("general","constitutional"):
    cmp("citation_1191",m,[r["domain"]=="constitutional" and not r["urdu"] for r in rows],"1191 constitutional & English")
cmp("citation_1191","general",[not r["urdu"] for r in rows],"1191 English-only")
