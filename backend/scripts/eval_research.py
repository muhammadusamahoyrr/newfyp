"""Lawyer AI Research eval: the REAL `/ai/research` route on a labelled set.

    python scripts/eval_research.py run   --label on_r1  --flag on
    python scripts/eval_research.py run   --label off_r1 --flag off
    python scripts/eval_research.py score evals/research/results/*_2026-10-14.jsonl

What is real: `ai_research` itself (request model, case authorisation through
case_service.get_case, the research state it builds, follow-up overrides, the
flag), the compiled chat graph with its Mongo checkpointer (local overlay DB),
retrieval over the embedded Chroma corpus, and the live model providers.

What is replaced, and why:
  * the conversation store and turn ledger -> tests/_conversation_fakes (in
    memory; the route's own logic still runs against them);
  * provenance.record_outcome -> captured, so the trace spans give per-turn
    model names and provider failures without writing audit records;
  * case_repo / user_repo lookups -> a synthetic case owned by the eval lawyer,
    so authorisation is the real rule applied to fixture data;
  * the semantic result cache -> OFF, so a repeated run is a new run and not a
    replay of the previous one.

Writes <label>.jsonl and <label>.manifest.json. Checkpoints written by the run
are deleted at the end (their thread ids are derived exactly as the route
derives them). Secrets are never read or recorded: the overlay values are
loaded into the environment only.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import re
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

import eval_chat_length as E   # noqa: E402  (overlay + identity helpers, shared on purpose)

DATASET_V1 = BACKEND_DIR / "evals" / "research" / "questions_v1.jsonl"
# v2 = the same 29 questions + proposition-level labels + adversarial A1-A4 (all SILVER).
DATASET = BACKEND_DIR / "evals" / "research" / "questions_v3.jsonl"
RESULTS = BACKEND_DIR / "evals" / "research" / "results"
LAWYER = {"_id": "eval-lawyer", "role": "lawyer", "full_name": "Eval Lawyer", "email": "eval@example.invalid",
          "is_active": True}
_LANGUAGE = {"en": "en", "ur": "ur", "roman_ur": "en"}


def load_items(path: Path = DATASET) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("//")]


async def _run(label: str, flag: bool, pause: float, only: set[str] | None, dataset: Path = DATASET) -> Path:
    E._apply_overlay()
    from _pytest.monkeypatch import MonkeyPatch

    from app.ai import cache as result_cache
    from app.ai import case_context as case_context_mod
    from app.ai.corpus_index import get_index
    from app.ai.intent import warmup as intent_warmup
    from app.ai.pipelines.law_graph import get_graph
    from app.ai.pipelines.retriever import _embeddings
    from app.api.v1.routes import ai as ai_routes
    from app.core.config import settings
    from app.db.chroma import connect_chroma
    from app.db.collections import get_checkpoint_writes_col, get_checkpoints_col
    from app.db.mongodb import close_db, connect_db
    from app.services import case_service, provenance_outbox
    from tests import _conversation_fakes as fakes

    items = [i for i in load_items(dataset) if not only or i["id"] in only]
    mp = MonkeyPatch()
    mp.setattr(settings, "research_answer_safeguards", flag)
    mp.setattr(result_cache, "get_redis", lambda: None)
    result_cache._result_store.clear()

    captured: dict = {}

    async def record_outcome(**kw):
        captured["spans"] = kw.get("spans") or []
        captured["state"] = kw.get("state") or {}
        return provenance_outbox.DURABLE, f"eval-{uuid.uuid4().hex[:10]}"
    mp.setattr(ai_routes.provenance_service, "record_outcome", record_outcome)

    cases: dict[str, dict] = {}

    async def find_case(cid):
        return cases.get(cid)

    async def find_user(uid):
        return {"_id": uid, "full_name": "Eval Client", "email": "client@example.invalid"}
    mp.setattr(case_service.case_repo, "find_by_id", find_case)
    mp.setattr(case_service.user_repo, "find_by_id", find_user)

    class _Counter(logging.Handler):
        def __init__(self):
            super().__init__(logging.WARNING)
            self.counts = defaultdict(int)

        def emit(self, record):
            msg = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                msg += " " + str(record.exc_info[1])
            for k in ("tool_use_failed", "output_parse_failed", "rate_limit", "429", "timeout"):
                if k in msg:
                    self.counts[k] += 1
    counter = _Counter()
    logging.getLogger().addHandler(counter)

    await connect_db()
    connect_chroma()
    await intent_warmup()
    for fn in (_embeddings, get_graph, get_index):
        await asyncio.to_thread(fn)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{label}.jsonl"
    if out.exists():
        raise SystemExit(f"{out.name} exists -- every run gets its own file")
    started = dt.datetime.now(dt.timezone.utc)
    corpus = E._corpus_identity()
    try:   # the versioned research indexes are not in the shared helper's filter
        from app.db.chroma import get_chroma
        for name in ("civil_collection__ident_v1", "criminal_collection__sec_v2"):
            corpus["collections"][name] = get_chroma().get_collection(name).count()
    except Exception as exc:
        corpus["research_index_error"] = type(exc).__name__
    manifest = {"label": label, "method": "route-v1 (real ai_research)", "started_utc": started.isoformat(),
                "research_answer_safeguards": flag,
                "dataset": {"path": dataset.relative_to(BACKEND_DIR).as_posix(),
                            "sha256": E._sha256(dataset.read_bytes()), "only": sorted(only or []),
                            "items": len(items), "turns": sum(len(i["turns"]) for i in items)},
                "code": E._code_identity(), "corpus": corpus, **E._settings_identity(),
                "result_cache": "disabled for the run",
                "env_overlay": ".env.analyzer-demo.local (values not recorded)"}
    threads: list[str] = []
    try:
        with out.open("w", encoding="utf-8") as fh:
            for it in items:
                conv, turns = fakes.install(mp, ai_routes)

                async def _noop(*a, **k):
                    return None
                mp.setattr(turns, "record_stage", _noop, raising=False)
                session = f"eval-{label}-{it['id']}-{uuid.uuid4().hex[:6]}"
                case_id = None
                if it.get("case"):
                    case_id = f"case-{it['id']}-{uuid.uuid4().hex[:6]}"
                    cases[case_id] = {"_id": case_id, "case_number": f"EV-{it['id']}", "status": "open",
                                      "province": "punjab", "client_id": "eval-client",
                                      "lawyer_id": LAWYER["_id"],
                                      "updated_at": "2026-10-14T00:00:00+00:00", **it["case"]}
                threads.append(case_context_mod.thread_id(LAWYER["_id"], session, case_id))
                for n, q in enumerate(it["turns"], 1):
                    body = ai_routes.ResearchRequest(
                        message=q, session_id=session, language=_LANGUAGE[it["lang"]], province="punjab",
                        history=[], case_id=case_id, client_message_id=uuid.uuid4().hex)
                    captured.clear()
                    t0 = time.perf_counter()
                    err, resp = None, {}
                    try:
                        resp = await ai_routes.ai_research(body, current_user=LAWYER)
                        resp = resp if isinstance(resp, dict) else resp.model_dump()
                    except Exception as exc:
                        err = f"{type(exc).__name__}: {str(exc)[:160]}"
                    ms = (time.perf_counter() - t0) * 1000
                    spans = captured.get("spans") or []
                    st = captured.get("state") or {}
                    kind = resp.get("type")
                    row = {"label": label, "flag": flag, "id": it["id"], "category": it["category"],
                           "lang": it["lang"], "turn": n, "query": q, "latency_ms": round(ms),
                           "error": err, "type": kind,
                           "answer": resp.get("answer") or resp.get("question") or "",
                           "citations": resp.get("citations") or [], "claims": resp.get("claims") or [],
                           "convergence": resp.get("convergence_status"),
                           "jurisdiction": resp.get("jurisdiction"),
                           "surface": st.get("surface"), "followup_intent": st.get("followup_intent"),
                           "case_type": st.get("case_type"),
                           "case_record_version": bool(st.get("case_record_version")),
                           "index_variant": (st.get("retrieval_policy") or {}).get("index_variant"),
                           "evidence": [{"id": e.get("id"), "kind": e.get("kind"), "statute": e.get("statute"),
                                         "section": e.get("section"), "label": e.get("label"),
                                         # opening text only: enough to tell WHICH provision it is
                                         "content": (e.get("content") or "")[:300]}
                                        for e in st.get("generation_evidence") or []],
                           "tools": [{"tool": t.get("tool"), "args": t.get("args"),
                                      "outcome": (t.get("result") or {}).get("outcome")
                                      if isinstance(t.get("result"), dict) else None,
                                      "result": str(t.get("result"))[:300]}
                                     for t in st.get("tool_results") or []],
                           "tool_conflicts": st.get("tool_conflicts") or [],
                           # sentences the period guard withheld -- the notice
                           # check needs WHAT was withheld, not just a notice
                           "periods_removed": st.get("periods_removed") or [],
                           "llm": [{"model": s.get("name"), "status": s.get("status"), "error": s.get("error")}
                                   for s in spans if s.get("kind") == "llm"]}
                    fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    fh.flush()
                    print(f"{it['id']}.{n} {str(kind):13} {ms / 1000:6.1f}s err={err and err[:60]}", flush=True)
                    await asyncio.sleep(pause)
    finally:
        for col in (get_checkpoints_col(), get_checkpoint_writes_col()):
            await col.delete_many({"thread_id": {"$in": threads}})
        await close_db()
        finished = dt.datetime.now(dt.timezone.utc)
        manifest.update({"finished_utc": finished.isoformat(),
                         "provider_log_counts": dict(counter.counts),
                         "checkpoints_deleted_for_threads": len(threads)})
        out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=1, default=str),
                                                    encoding="utf-8")
        mp.undo()
    return out


# ── scoring (automatic part; hand judgement is recorded separately) ─────────

def _rx(patterns):
    return [re.compile(p, re.I) for p in patterns]


# Models write "489‑F" (non-breaking hyphen) and " " spaces; the
# labels are plain ASCII. Scored text is folded first, or a correct answer
# counts as a miss.
_FOLD = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                       "−": "-", " ": " ", " ": " ", " ": " "})


def _fold(text: str) -> str:
    return (text or "").translate(_FOLD)


def score_rows(rows: list[dict], items: dict[str, dict]) -> dict:
    from app.ai import jurisdiction_guard
    per_item = []
    for it_id, it in items.items():
        turns = sorted((r for r in rows if r["id"] == it_id), key=lambda r: r["turn"])
        if not turns:
            continue
        last = turns[-1]
        text = _fold(" ".join(r["answer"] for r in turns if r["type"] == "final") or last["answer"])
        expect, forbid = _rx(it.get("expect_any") or []), _rx(it.get("forbid") or [])
        forbidden = [p.pattern for p in forbid if p.search(text)]
        supported_forbidden = [c.get("text", "")[:120] for r in turns for c in r["claims"]
                               if c.get("support") in ("supported", "partial")
                               and any(p.search(_fold(c.get("text", ""))) for p in forbid)]
        comparative = jurisdiction_guard.asks_comparative(" ".join(it["turns"]))
        foreign = [] if comparative else sorted(set(jurisdiction_guard.markers_in(text)))
        claims = [c for r in turns for c in r["claims"]]
        per_item.append({
            "id": it_id, "category": it["category"], "lang": it["lang"],
            "answerable": it.get("answerable"),
            "errors": [r["error"] for r in turns if r["error"]],
            "types": [r["type"] for r in turns],
            "expected_hit": (any(p.search(text) for p in expect) if expect else None),
            "forbidden_hits": forbidden, "supported_on_forbidden": supported_forbidden,
            "foreign_markers": foreign,
            "claims": len(claims),
            "supported": sum(c.get("support") == "supported" for c in claims),
            "unassessed": sum(c.get("support") == "unassessed" for c in claims),
            "unsupported": sum(c.get("support") == "unsupported" for c in claims),
            "matched_citations": sum(c.get("status") == "matched" for r in turns for c in r["citations"]),
            "followup_clarified": len(turns) > 1 and turns[-1]["type"] == "clarification",
            "latency_s": round(sum(r["latency_ms"] for r in turns) / 1000, 1),
        })

    def agg(group):
        n = len(group)
        hits = [g["expected_hit"] for g in group if g["expected_hit"] is not None]
        return {"items": n,
                "errors": sum(bool(g["errors"]) for g in group),
                "expected_hit": f"{sum(hits)}/{len(hits)}",
                "forbidden_in_answer": sum(bool(g["forbidden_hits"]) for g in group),
                "forbidden_marked_supported": sum(bool(g["supported_on_forbidden"]) for g in group),
                "foreign_markers": sum(bool(g["foreign_markers"]) for g in group),
                "followup_clarified": sum(g["followup_clarified"] for g in group),
                "claims": sum(g["claims"] for g in group),
                "supported": sum(g["supported"] for g in group),
                "unassessed": sum(g["unassessed"] for g in group),
                "matched_citations": sum(g["matched_citations"] for g in group),
                "median_latency_s": sorted(g["latency_s"] for g in group)[n // 2] if n else None}
    by_cat, by_lang = defaultdict(list), defaultdict(list)
    for g in per_item:
        by_cat[g["category"]].append(g)
        by_lang[g["lang"]].append(g)
    return {"overall": agg(per_item), "by_category": {k: agg(v) for k, v in sorted(by_cat.items())},
            "by_language": {k: agg(v) for k, v in sorted(by_lang.items())}, "items": per_item}


# ── score2: proposition-level (2026-10-14, tool-contract batch) ─────────────
#
# v1 scoring was keyword presence/absence, and it reported ZERO wrong
# statements marked supported on a run where E1's answer said Section 420 "does
# not match any known provision" with that claim SUPPORTED by PPC 420's own
# text. score2 reads each claim, the sources it cites and the provisions it
# names. Everything here is deterministic and SILVER: it checks the shape of a
# proposition against its cited source, not legal truth.

_ABSTAIN = re.compile(
    r"unable to provide a reliable answer|couldn't find the text|could not find the text|"
    r"could not produce a verified answer|not (?:available|present|included|contained) in the "
    r"(?:provided|supplied|retrieved|available)|no (?:section|provision)s? (?:relating|related) to|"
    r"cannot (?:be )?(?:confirm|determin)ed? from|text of .{0,40} was not found", re.I)


def _canon_section(sec: str) -> str:
    return re.sub(r"[\s\-]", "", (sec or "")).upper()


def _ev_key(e: dict) -> tuple[str, str] | None:
    from app.ai.answer_citations import normalise_statute
    if e.get("kind") not in (None, "statute") or not e.get("statute") or not e.get("section"):
        return None
    return normalise_statute(e["statute"]), _canon_section(e["section"])


def _ref_key(ref) -> tuple[str, str]:
    return ref.key[0], _canon_section(ref.section)


def score_rows_v2(rows: list[dict], items: dict[str, dict]) -> dict:
    from app.ai import tool_contract
    per = []
    for it_id, it in items.items():
        turns = sorted((r for r in rows if r["id"] == it_id), key=lambda r: r["turn"])
        if not turns:
            continue
        finals = [r for r in turns if r["type"] == "final"]
        last = turns[-1]
        answer = _fold(last["answer"] if last["type"] == "final" else (finals[-1]["answer"] if finals else ""))
        evidence = [e for r in turns for e in r.get("evidence") or []]
        ev_keys = {k for k in (_ev_key(e) for e in evidence) if k}
        named = tool_contract.provision_refs(" ".join(it["turns"]))
        exact_hit = None
        if named:
            exact_hit = all(_ref_key(r) in ev_keys for r in named)

        # (1) false "not found": the final answer denies a provision the corpus
        # has (answerable item) -- a CONTRADICTION when its text was in evidence.
        denied = []
        for sentence in re.split(r"(?<=[.!?۔])\s+|\n+", answer):
            denied += [r for r in tool_contract._denied_refs(sentence)]
        denied_keys = {_ref_key(r) for r in denied}
        named_keys = {_ref_key(r) for r in named}
        false_not_found = bool(it.get("answerable")) and bool(denied_keys & named_keys)
        contradiction = bool(denied_keys & ev_keys)

        # (2) false-supported claims, judged on the proposition and its source.
        false_supported = []
        for r in turns:
            by_id = {e.get("id"): e for e in r.get("evidence") or []}
            for c in r.get("claims") or []:
                if c.get("support") not in ("supported", "partial") or c.get("removed_from_answer"):
                    continue
                text = _fold(c.get("text", ""))
                cited = [by_id[i] for i in c.get("source_ids") or [] if i in by_id]
                cited_keys = {k for k in (_ev_key(e) for e in cited) if k}
                why = None
                if {_ref_key(x) for x in tool_contract._denied_refs(text)} & (cited_keys | named_keys):
                    why = "denies a provision its source / the question names"
                else:
                    claim_refs = {_ref_key(x) for x in tool_contract.provision_refs(text)}
                    statute_cited = [e for e in cited if e.get("kind") in (None, "statute")]
                    if claim_refs and statute_cited and not (claim_refs & cited_keys):
                        why = "names a provision none of its cited sources is"
                    elif any(re.search(p, text, re.I) for p in it.get("forbid") or []):
                        why = "states a labelled-wrong proposition"
                if why:
                    false_supported.append({"turn": r["turn"], "why": why, "text": c.get("text", "")[:140]})

        visible = _visible_violations(it, turns)

        facts = it.get("expect_facts") or []
        facts_hit = [bool(re.search(f, answer, re.I)) for f in facts]
        abstained = bool(_ABSTAIN.search(answer)) or not answer.strip()
        conflicts = [c for r in turns for c in r.get("tool_conflicts") or []]
        tools = [t for r in turns for t in r.get("tools") or []]
        per.append({
            "id": it_id, "category": it["category"], "lang": it["lang"], "label_tier": it.get("label_tier", "silver"),
            "answerable": it.get("answerable"), "types": [r["type"] for r in turns],
            "errors": [r["error"] for r in turns if r["error"]],
            "provider_errors": sum(1 for r in turns for s in r.get("llm") or [] if s.get("status") == "error"),
            "named": [f"{k[0]} {k[1]}" for k in sorted(named_keys)], "exact_provision_hit": exact_hit,
            "false_not_found": false_not_found, "contradiction_in_answer": contradiction,
            "false_supported": false_supported,
            "complete": (all(facts_hit) and not abstained) if facts else None,
            "abstained": abstained,
            "correct_abstention": abstained and it.get("abstain_expected", False),
            "missed_answer": abstained and bool(it.get("answerable")),
            "tool_calls": [{"tool": t["tool"], "outcome": t.get("outcome")} for t in tools],
            "conflicts_resolved": [c.get("resolution") for c in conflicts],
            "latency_s": round(sum(r["latency_ms"] for r in turns) / 1000, 1),
            **visible,
        })

    def agg(g):
        n = len(g)
        named = [x for x in g if x["exact_provision_hit"] is not None]
        comp = [x for x in g if x["complete"] is not None]
        lat = sorted(x["latency_s"] for x in g)
        return {"items": n,
                "exact_provision_hit": f"{sum(x['exact_provision_hit'] for x in named)}/{len(named)}",
                "false_not_found": sum(x["false_not_found"] for x in g),
                "contradiction_in_answer": sum(x["contradiction_in_answer"] for x in g),
                "items_with_false_supported": sum(bool(x["false_supported"]) for x in g),
                "false_supported_claims": sum(len(x["false_supported"]) for x in g),
                "complete": f"{sum(x['complete'] for x in comp)}/{len(comp)}",
                "abstained": sum(x["abstained"] for x in g),
                "correct_abstentions": sum(x["correct_abstention"] for x in g),
                "missed_answers": sum(x["missed_answer"] for x in g),
                "conflicts_resolved": sum(len(x["conflicts_resolved"]) for x in g),
                "tool_outcomes": _count(t["outcome"] or "legacy" for x in g for t in x["tool_calls"]),
                # release blockers, read from the FINAL visible answer
                "whole_act_silence": sum(bool(x["whole_act_silence"]) for x in g),
                "invalid_authority_visible": sum(bool(x["invalid_authority_visible"]) for x in g),
                "unverified_authority_visible": sum(bool(x["unverified_authority_visible"]) for x in g),
                "notice_contradiction": (sum(bool(x["notice_contradiction"]) for x in g)
                                         if not any(x["notice_unmeasured"] for x in g) else "not measured"),
                "governing_hit": f"{sum(x['governing_rank'] is not None for x in g if x['governing_label'])}"
                                 f"/{sum(bool(x['governing_label']) for x in g)}",
                "turn_errors": sum(len(x["errors"]) for x in g),
                "provider_errors": sum(x["provider_errors"] for x in g),
                "median_latency_s": lat[n // 2] if n else None,
                "p90_latency_s": lat[min(n - 1, int(n * 0.9))] if n else None}
    by_cat, by_lang = defaultdict(list), defaultdict(list)
    for x in per:
        by_cat[x["category"]].append(x)
        by_lang[x["lang"]].append(x)
    return {"scorer": "score2 (proposition-level, SILVER labels)",
            "overall": agg(per), "by_category": {k: agg(v) for k, v in sorted(by_cat.items())},
            "by_language": {k: agg(v) for k, v in sorted(by_lang.items())}, "items": per}


_CORPUS_READY = {"ok": None}


def _corpus_ready() -> bool:
    """The authority check reads the corpus (exact text + heading index)."""
    if _CORPUS_READY["ok"] is None:
        try:
            E._apply_overlay()
            from app.db.chroma import connect_chroma
            connect_chroma()
            from app.ai import corpus_index
            corpus_index.get_index()
            _CORPUS_READY["ok"] = True
        except Exception as exc:
            print(f"score2: corpus unavailable ({type(exc).__name__}); authority checks skipped")
            _CORPUS_READY["ok"] = False
    return _CORPUS_READY["ok"]


def _visible_violations(it: dict, turns: list[dict]) -> dict:
    """Release blockers read from the FINAL text each turn showed -- not from
    which claims were marked supported (RU2 d2 showed "bail under Section 438
    CrPC" with every chip saying unresolved, and scored 0 wrong-supported)."""
    from app.ai import period_support, visible_authority
    from app.ai.answer_citations import normalise_statute
    question = " ".join(it["turns"])
    urdu = it["lang"] == "ur"
    silence, invalid, unverified, contradiction, notice_unmeasured = [], [], [], [], []
    notices = (period_support.RESEARCH_NOTICE_EN, period_support.RESEARCH_NOTICE_UR,
               period_support.NOTICE_EN, period_support.NOTICE_UR)
    for r in turns:
        if r["type"] != "final":
            continue
        answer = r["answer"]
        _, replaced = visible_authority.whole_act_silence(answer, question, "punjab", urdu)
        silence += [s[:140] for s in replaced]
        if _corpus_ready():
            _, withheld = visible_authority.authorities(answer, question, urdu, research=True,
                                                        evidence=r.get("evidence") or [])
            for w in withheld:
                for p in w["problems"]:
                    row = {"turn": r["turn"], "label": p["label"], "status": p["status"], "text": w["text"][:140]}
                    (unverified if p["status"] == "unverified" else invalid).append(row)
        # A notice contradicts the answer when a period it says was withheld
        # is still shown. Needs the withheld sentences (recorded from the
        # tool-contract batch on); older rows are not measured.
        if "periods_removed" in r:
            withheld = {p for s in r["periods_removed"] for p, _ in period_support.periods_in(s)}
            for notice in notices:
                if notice in answer and withheld & {p for p, _ in period_support.periods_in(answer.replace(notice, " "))}:
                    contradiction.append(r["turn"])
        else:
            notice_unmeasured.append(r["turn"])
    rank = None
    label = it.get("governing")
    if label:
        statute, section = label.rsplit(":", 1)
        for i, e in enumerate((turns[0].get("evidence") or []), 1):
            if normalise_statute(e.get("statute") or "") == normalise_statute(statute) and \
                    _canon_section(e.get("section") or "") == _canon_section(section):
                rank = i
                break
    return {"whole_act_silence": silence, "invalid_authority_visible": invalid,
            "unverified_authority_visible": unverified, "notice_contradiction": contradiction,
            "notice_unmeasured": bool(notice_unmeasured),
            "governing_label": label, "governing_rank": rank}


def _count(values) -> dict:
    out: dict = defaultdict(int)
    for v in values:
        out[v] += 1
    return dict(sorted(out.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--flag", choices=("on", "off"), required=True)
    r.add_argument("--pause", type=float, default=4.0)
    r.add_argument("--only", default="")
    r.add_argument("--dataset", default=str(DATASET))
    s = sub.add_parser("score")
    s.add_argument("files", nargs="+")
    s2 = sub.add_parser("score2")
    s2.add_argument("files", nargs="+")
    a = ap.parse_args()
    if a.cmd == "run":
        only = {x for x in a.only.split(",") if x} or None
        print(asyncio.run(_run(a.label, a.flag == "on", a.pause, only, Path(a.dataset))))
        return
    if a.cmd == "score2":
        items = {i["id"]: i for i in load_items(DATASET)}
        for f in a.files:
            p = Path(f)
            rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
            ids = {r["id"] for r in rows}
            result = score_rows_v2(rows, {k: v for k, v in items.items() if k in ids})
            p.with_name(p.stem + "_score2.json").write_text(json.dumps(result, indent=1, ensure_ascii=False),
                                                           encoding="utf-8")
            print(p.stem, json.dumps(result["overall"], ensure_ascii=False))
        return
    items = {i["id"]: i for i in load_items(DATASET_V1)}
    for f in a.files:
        p = Path(f)
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        result = score_rows(rows, items)
        p.with_name(p.stem + "_score.json").write_text(json.dumps(result, indent=1, ensure_ascii=False),
                                                      encoding="utf-8")
        print(p.stem, json.dumps(result["overall"]))


if __name__ == "__main__":
    main()
