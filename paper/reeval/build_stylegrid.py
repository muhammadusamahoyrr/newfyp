"""Style grid for the FIT paper: hold each question's CONTENT (and gold passage)
fixed and vary only its STYLE, to test whether a fine-tuned retriever's gain
depends on question style.

Content sets (gold clean for the model they are used with):
  uqa128 -- 128 LEGAL-UQA questions, no gold shared with general training
  uqa121 -- the constitutional model's own 121 held-out questions
  dev23  -- developer-written queries clean for the general model at the
            section level (paper/reeval/section_leak.py)
Styles: original; urdu (dataset's own translation for LEGAL-UQA, generated for
dev23); layperson_en; roman_urdu; keyword.  Generated styles come from one
LLM call per question (backend LLM routing, purpose answer_reformat) and are
rejected if they add any number or an article/section reference the original
lacks. Checkpointed to stylegrid_raw.json, so a rerun resumes.

Usage: backend/venv/Scripts/python.exe paper/reeval/build_stylegrid.py
"""
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
from app.ai.llm import get_llm  # noqa: E402
from app.ai.provider_health import PURPOSE_ANSWER_REFORMAT  # noqa: E402

DATA = BACKEND / "data"
RAW = HERE / "stylegrid_raw.json"
DEV23 = ["d004", "d005", "d006", "d007", "d008", "d010", "d019", "d020", "d021", "d025", "d031", "c003",
         "c004", "c007", "c009", "c012", "c013", "c015", "c018", "c020", "l009", "v001", "m004"]

PROMPT = """You rewrite a legal question in different styles WITHOUT changing what it asks.
Rules for every style:
- Same legal question, same facts; do not answer it, do not add facts, names, numbers, or legal citations.
- Mention an article or section number ONLY if the original mentions it.
Styles:
- Keep who or what the question is about: never turn a question about an institution or a rule into a \
question about the asker ("Can the Assembly vote on X?" must stay about the Assembly).
- "layperson_en": the same question as an ordinary Pakistani citizen with no legal training would word it in \
plain English, replacing legal jargon with everyday words.
- "roman_urdu": how a Pakistani would type it in Roman Urdu (Urdu in English letters), informal.
- "keyword": a short search-box query of 3 to 8 keywords, no full sentence.{urdu_rule}
Return ONLY a JSON object with the keys {keys}."""
URDU_RULE = '\n- "urdu": the question in standard Urdu script.'

items = []
for i, t in enumerate(json.load(open(DATA / "crossstyle_test.json", encoding="utf-8"))):
    items.append({"id": f"uqa128_{i:03d}", "content": "uqa128", "original": t["question"],
                  "urdu": t["question_urdu"], "gold": t["relevant_chunks"]})
for i, t in enumerate(json.load(open(DATA / "finetune" / "test_questions.json", encoding="utf-8"))):
    items.append({"id": f"uqa121_{i:03d}", "content": "uqa121", "original": t["question"],
                  "urdu": t["question_urdu"], "gold": t["relevant_chunks"]})
third = {r["query_id"]: r for r in json.load(open(HERE / "thirdstyle_test.json", encoding="utf-8"))}
for qid in DEV23:
    r = third[qid]
    items.append({"id": f"dev23_{qid}", "content": "dev23", "original": r["query"], "urdu": None,
                  "gold": r["relevant_chunks"], "lang": r["language"]})

raw = json.load(open(RAW, encoding="utf-8")) if RAW.exists() else {}
NUM = re.compile(r"\d+")
REF = re.compile(r"\b(article|section|art\.|s\.)\s*\d|آرٹیکل|دفعہ|\bdafa\b", re.IGNORECASE)


def valid(original, text):
    if not text or not text.strip():
        return False
    if set(NUM.findall(text)) - set(NUM.findall(original)):
        return False
    if REF.search(text) and not REF.search(original):
        return False
    return True


llm = get_llm(purpose=PURPOSE_ANSWER_REFORMAT)
todo = [it for it in items if it["id"] not in raw]
print(f"items: {len(items)}  already done: {len(items) - len(todo)}  to do: {len(todo)}", flush=True)
for n, it in enumerate(todo, 1):
    keys = ["layperson_en", "roman_urdu", "keyword"] + (["urdu"] if it["urdu"] is None else [])
    prompt = PROMPT.format(urdu_rule=URDU_RULE if it["urdu"] is None else "", keys=", ".join(f'"{k}"' for k in keys))
    out = None
    for attempt in range(3):
        try:
            resp = llm.invoke([{"role": "system", "content": prompt},
                               {"role": "user", "content": it["original"]}])
            txt = resp.content.strip()
            txt = txt[txt.find("{"): txt.rfind("}") + 1]
            out = json.loads(txt)
            if all(k in out for k in keys):
                break
        except Exception as e:  # noqa: BLE001
            print(f"  {it['id']} attempt {attempt + 1}: {type(e).__name__}", flush=True)
            time.sleep(3)
        out = None
    if out is None:
        print(f"  {it['id']}: FAILED", flush=True)
        continue
    raw[it["id"]] = {k: (out[k] if valid(it["original"], out[k]) else None) for k in keys}
    if n % 10 == 0 or n == len(todo):
        json.dump(raw, open(RAW, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  {n}/{len(todo)}", flush=True)

json.dump(raw, open(RAW, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

rows, rejected = [], 0
for it in items:
    gen = raw.get(it["id"], {})
    styles = {"original": it["original"], "urdu": it["urdu"] if it["urdu"] is not None else gen.get("urdu")}
    for k in ("layperson_en", "roman_urdu", "keyword"):
        styles[k] = gen.get(k)
    for style, q in styles.items():
        if q is None:
            rejected += 1
            continue
        src = "dataset" if style == "original" or (style == "urdu" and it["urdu"] is not None) else "generated"
        rows.append({"item": it["id"], "content": it["content"], "style": style, "source": src,
                     "query": q, "relevant_chunks": it["gold"]})
json.dump(rows, open(HERE / "stylegrid_test.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"rows: {len(rows)}  missing/rejected style cells: {rejected}")
