"""Provider claim-check pilot for input-fact fidelity -- SYNTHETIC TEXT ONLY, DEV ONLY (2026-10-15).

Question asked of the model, one sentence at a time: which facts does this drafted sentence state that the lawyer's
input does not? Items are synthetic: the drafter's own sentences on the synthetic eval cases, the synthetic probe, and
the Urdu probe -- never Desktop/error source text, never a real person. Labels are LOCKED (sha256) before anything is
sent and are never sent.

  python scripts/claim_check_pilot.py preview            # builds the payloads, privacy-checks them; sends NOTHING
  python scripts/claim_check_pilot.py run --approved     # only after the user approves the preview

Pinned to ONE provider/model (no failover): groq3 / openai/gpt-oss-120b, at the app's own Groq temperature (0.1). Not wired into the drafter;
a pilot result is a measurement, never a release claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]
DIR = BACKEND / "evals/drafter_v2/claim_check_pilot"
PROVIDER, MODEL = "groq3", "openai/gpt-oss-120b"

SYSTEM = """You check one sentence of a legal draft against the lawyer's own input.
List every FACT the sentence states as true that the INPUT does not state: a person's condition or conduct, an event,
a date, period, amount, number, name or place, or a contract term chosen for the parties.
NOT facts: statements of law, requests to the court, undertakings, and anything in [square brackets] or blanks (____).
A fact the INPUT states, even in other words, is not new.
Reply with JSON only: {"new_facts": ["<short quote from the sentence>", ...]} -- an empty list when there are none."""


def pilot_items() -> list[dict]:
    """23 items: real drafter sentences (every 2nd invented, up to 10; every 12th clean one without blanks -> 9),
    plus Urdu 2 invented / 2 ok.
    Chosen by a fixed rule, not by any method's output."""
    dev = json.loads((BACKEND / "evals/drafter_v2/fact_fidelity_dev.json").read_text(encoding="utf-8"))["rows"]
    real = [r for r in dev if not str(r["n"]).startswith("U")]
    inv = [r for r in real if r["label"] == "invented"]
    ok = [r for r in real if r["label"] == "ok" and "[" not in r["sentence"] and "___" not in r["sentence"]]
    picked = inv[::2][:10] + ok[::12][:10]
    urdu = [r for r in dev if str(r["n"]).startswith("U")]
    picked += [u for u in urdu if u["label"] == "invented"][:2] + [u for u in urdu if u["label"] == "ok"][:2]
    return [{"id": f"P{i + 1:02d}", "source": f"dev#{r['n']}", "input": r["input"], "sentence": r["sentence"],
             "label": r["label"], "fact": r.get("fact", "")} for i, r in enumerate(picked)]


def payload(item: dict) -> list[dict]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"INPUT:\n{item['input'].strip()}\n\nSENTENCE:\n{item['sentence'].strip()}"}]


def preview() -> dict:
    import eval_drafter_v2 as V
    items = pilot_items()
    DIR.mkdir(parents=True, exist_ok=True)
    labels = [{"id": it["id"], "label": it["label"], "fact": it["fact"]} for it in items]
    raw = (json.dumps(labels, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    (DIR / "labels.developer.json").write_bytes(raw)
    (DIR / "labels.developer.lock.json").write_text(json.dumps(
        {"sha256": hashlib.sha256(raw).hexdigest(), "locked": "2026-10-15", "by": "developer (provisional)",
         "note": "Locked BEFORE any request is sent. Not sent to the provider. Independent labels go in "
                 "labels.independent.json from blind_sheet.md, by someone who has seen neither these labels nor outputs."},
        indent=1), encoding="utf-8")
    sheet = ["# Claim-check pilot -- blind labelling sheet (for an independent labeller)", "",
             "For each item: does the SENTENCE state a fact or contract term the INPUT does not give? Write the id, "
             "`invented` or `ok`, and the words. Statements of law, requests, undertakings and [placeholders] are not facts.",
             "Do not look at labels.developer.json or any model output first.", ""]
    for it in items:
        sheet += [f"## {it['id']}", f"INPUT: {it['input'].strip()[:600]}", "", f"SENTENCE: {it['sentence'].strip()}", ""]
    (DIR / "blind_sheet.md").write_text("\n".join(sheet), encoding="utf-8")
    payloads = [payload(it) for it in items]
    chk = V.payload_check(payloads, V.DEFAULT_SRC)
    prev = {"provider": PROVIDER, "model": MODEL, "failover": "none (pinned)", "temperature": 0.1,
            "calls": len(items), "runs": 1, "items": len(items),
            "composition": {"invented": sum(i["label"] == "invented" for i in items),
                            "ok": sum(i["label"] == "ok" for i in items),
                            "urdu": sum(i["source"].startswith("dev#U") for i in items)},
            "never_sent": ["labels", "Desktop/error source documents", "any real person's data", "API keys"],
            "privacy_check": {k: v for k, v in chk.items() if k != "per_payload"},
            "requests": [{"id": it["id"], "messages": p} for it, p in zip(items, payloads)]}
    (DIR / "transmit_preview.json").write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    return prev


def run() -> int:
    """Sends the previewed requests -- ONLY with --approved. One call per item, no retries, no failover."""
    import asyncio
    import eval_chat_length as EC
    EC._apply_overlay()
    from app.ai import llm
    prev = json.loads((DIR / "transmit_preview.json").read_text(encoding="utf-8"))
    model = llm._built_model(PROVIDER, MODEL)
    out = []

    async def one(req):
        try:
            msg = await model.ainvoke([(m["role"], m["content"]) for m in req["messages"]])
            text = getattr(msg, "content", "") or ""
            try:
                facts = json.loads(text[text.find("{"):text.rfind("}") + 1]).get("new_facts", [])
            except Exception:
                facts = None
            return {"id": req["id"], "raw": text[:2000], "new_facts": facts, "error": None}
        except Exception as e:                       # recorded, never retried elsewhere
            # the provider's own message (the 2026-10-15 run kept only the type -- 23 x BadRequestError, cause
            # unknown); anything key-like is redacted before it is stored
            import re
            detail = re.sub(r"(?i)(gsk_|sk-|key[\"'=: ]+)[\w-]{6,}", r"\1<redacted>", str(e))[:400]
            return {"id": req["id"], "raw": "", "new_facts": None, "error": type(e).__name__, "detail": detail}
    for req in prev["requests"]:
        out.append(asyncio.run(one(req)))
    (DIR / "results.jsonl").write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n", encoding="utf-8")
    print(f"{len(out)} calls, errors: {sum(1 for o in out if o['error'])}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preview")
    r = sub.add_parser("run")
    r.add_argument("--approved", action="store_true")
    a = ap.parse_args()
    if a.cmd == "preview":
        p = preview()
        print(json.dumps({k: v for k, v in p.items() if k != "requests"}, indent=1, ensure_ascii=False))
        return 0
    if not a.approved:
        print("Refusing: the pilot sends requests only with --approved, after the user approves the preview.")
        return 2
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
