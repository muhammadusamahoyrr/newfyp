"""eval_chat_length.py — client-chat answer length vs completeness (2026-10-13).

  python scripts/eval_chat_length.py run    --label baseline --out evals/chat_length/results/baseline.jsonl [--ids c01,c02]
  python scripts/eval_chat_length.py assess --runs evals/chat_length/results/baseline.jsonl[,after.jsonl] [--out R.json]

RUN (default --method socket) drives chat_socket.chat_endpoint itself -- see
_run_socket -- and writes <out>.manifest.json (code / dataset / corpus /
settings identity, failures). --method thread is the older runner below.
The thread runner drives the REAL client-chat turn logic in-process, against the local demo
database (the `.env.analyzer-demo.local` overlay is applied before any app
import, so the hosted database is never touched):
  * the same intent classifier the socket uses, and the same routing: an
    intent the socket would answer by shortcut is answered the same way
    (`chat_socket.client_turn_overrides` when it exists, the legacy
    `_reformat` shortcut otherwise -- so one runner measures before and after);
  * `chat_socket._build_state` + `chat_graph.ainvoke`, with a throwaway
    thread id; an interrupt (clarifying question) is recorded as such.
  Every eval checkpoint is deleted at the end (threads `evalchat-*`).

ASSESS is deterministic and reads only the stored records:
  words (disclaimer excluded), required law / deadline / warning retention,
  citations (and how many the finalizer could not match), repetition inside an
  answer and against the previous turn, latency. A shorter answer that drops a
  required element counts as a REGRESSION, not a win. Labels are silver.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATASET = BACKEND_DIR / "evals" / "chat_length" / "questions_v1.jsonl"
THREAD_PREFIX = "evalchat-"


def _apply_overlay() -> None:
    spec = importlib.util.spec_from_file_location("serve_for_overlay", BACKEND_DIR / "scripts" / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    os.environ.update(mod.read_env_overlay(BACKEND_DIR / ".env.analyzer-demo.local"))


def load_items(path: Path = DATASET) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("//")]


# ── run ──────────────────────────────────────────────────────────────────────

async def _run(items: list[dict], out: Path, label: str, pause: float) -> None:
    _apply_overlay()
    from app.ai.graph.supervisor import chat_graph
    from app.ai.intent import classify as intent_classify
    from app.db.chroma import connect_chroma
    from app.db.collections import get_checkpoint_writes_col, get_checkpoints_col
    from app.db.mongodb import close_db, connect_db
    from app.websockets import chat_socket as cs
    await connect_db()
    connect_chroma()
    language_of = {"en": "en", "ur": "ur", "roman_ur": "en"}
    threads = []
    try:
        with out.open("w", encoding="utf-8") as fh:
            for it in items:
                history: list[dict] = []
                last_ai = None
                thread = f"{THREAD_PREFIX}{uuid.uuid4().hex[:12]}"
                threads.append(thread)
                for n, turn in enumerate(it["turns"], 1):
                    q = turn["q"]
                    t0 = time.perf_counter()
                    intent = await intent_classify(text=q, session_id=thread, history=list(history))
                    data = {"language": language_of[it["lang"]], "province": "punjab"}
                    session = {"province": "punjab"}
                    route, rec = "graph", {}
                    overrides_fn = getattr(cs, "client_turn_overrides", None)
                    if overrides_fn is None and intent.intent == "format_brief" and last_ai:
                        route = "legacy_reformat"
                        answer = await cs._reformat(q, last_ai)
                        rec = {"answer": answer, "citations": [], "claims": [], "convergence": "converged",
                               "is_grounded": False, "response_mode": None}
                    else:
                        state = cs._build_state(q, thread, session, data, history=list(history),
                                                user_id="eval-user", user_role="client")
                        if overrides_fn is not None:
                            # Mirror the socket: the trusted route sets the surface.
                            state["surface"] = "client"
                            state.update(overrides_fn(intent.intent, list(history), last_ai))
                        elif intent.intent == "format_detail":
                            state["followup_intent"] = "deepen"
                        config = {"configurable": {"thread_id": f"{thread}-{n}"}}
                        threads.append(f"{thread}-{n}")
                        try:
                            await chat_graph.ainvoke(state, config=config)
                            graph_error = None
                        except Exception as exc:  # a provider fault fails this turn, not the run
                            graph_error = type(exc).__name__
                        snap = await chat_graph.aget_state(config=config)
                        question = cs._extract_interrupt_question(snap)
                        v = snap.values
                        if graph_error:
                            rec = {"answer": "", "citations": [], "claims": [], "convergence": "error",
                                   "is_grounded": None, "response_mode": v.get("response_mode"),
                                   "error": graph_error}
                        elif question is not None:
                            rec = {"answer": question, "citations": [], "claims": [], "convergence": "clarification",
                                   "is_grounded": None, "response_mode": v.get("response_mode")}
                        else:
                            rec = {"answer": v.get("answer", ""), "citations": v.get("citations", []),
                                   "claims": v.get("claim_assessments", []),
                                   "convergence": v.get("convergence_status"), "is_grounded": v.get("is_grounded"),
                                   "response_mode": v.get("response_mode"),
                                   "followup_intent": v.get("followup_intent"),
                                   "complexity": v.get("complexity")}
                    ms = (time.perf_counter() - t0) * 1000
                    row = {"label": label, "id": it["id"], "lang": it["lang"], "category": it["category"],
                           "turn": n, "query": q, "intent": intent.intent, "route": route,
                           "latency_ms": round(ms, 1), **rec}
                    fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    fh.flush()
                    print(f"{it['id']}.{n} {it['lang']:8} {intent.intent:12} {route:15} "
                          f"{len(_words(rec['answer'])):4}w {ms / 1000:5.1f}s mode={rec.get('response_mode')}",
                          flush=True)
                    history += [{"role": "user", "content": q}, {"role": "assistant", "content": rec["answer"]}]
                    last_ai = rec["answer"]
                    if pause:
                        await asyncio.sleep(pause)
    finally:
        # Remove every eval checkpoint (temporary data of this run only).
        for col in (get_checkpoints_col(), get_checkpoint_writes_col()):
            await col.delete_many({"thread_id": {"$regex": f"^{THREAD_PREFIX}"}})
        await close_db()


# ── run through the REAL socket (method "socket-v1", 2026-10-13) ─────────────
#
# The thread runner above starts a fresh graph thread per turn. The socket does
# not: its thread IS the session, so a second turn sent while a clarification
# is pending is consumed as the answer to it, and state carries between turns.
# Measured follow-up behaviour differed between the two. This runner drives
# `chat_socket.chat_endpoint` itself, one message per connection, against the
# real compiled graph and its Mongo checkpointer on the local overlay database.
# Faked, exactly as tests/test_chat_socket.py fakes them: the login ticket, the
# users lookup, the conversation store and turn ledger (in-memory, still
# server-side), and the provenance writer (its arguments are captured: the
# trace spans give per-turn model names and failure classes).

_SECRET_HINTS = ("key", "secret", "token", "password", "passwd", "uri", "url", "dsn", "auth", "credential")
_SOURCE_GLOBS = ("app/**/*.py", "scripts/eval_chat_length.py", "scripts/serve.py")


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _code_identity() -> dict:
    """Hashes only -- never file contents."""
    import subprocess
    files = sorted({p for g in _SOURCE_GLOBS for p in BACKEND_DIR.glob(g) if p.is_file()})
    per_file = [(p.relative_to(BACKEND_DIR).as_posix(), _sha256(p.read_bytes())) for p in files]
    combined = _sha256("\n".join(f"{n} {h}" for n, h in per_file).encode())

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=BACKEND_DIR, capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=60).stdout.strip()
        except Exception:
            return None
    key_files = ("app/ai/response_policy.py", "app/ai/period_support.py", "app/websockets/chat_socket.py",
                 "app/ai/nodes/triage_node.py", "app/ai/graph/edges.py", "app/ai/nodes/finalizer_node.py",
                 "app/ai/nodes/hallucination_node.py", "app/ai/answer_citations.py",
                 "app/ai/nodes/generation_node.py", "app/ai/nodes/classifier_node.py",
                 "app/ai/nodes/fact_gap_node.py", "app/ai/cache.py")
    return {"source_fingerprint": combined, "files_hashed": len(per_file),
            "key_files": {n: h for n, h in per_file if n in key_files},
            "git_head": git("rev-parse", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain", "--", ".")),
            "git_diff_sha256": _sha256((git("diff", "HEAD", "--", ".") or "").encode())}


def _corpus_identity() -> dict:
    from app.ai import cache as result_cache
    from app.ai.pipelines import retriever
    from app.db.chroma import get_chroma
    counts = {}
    try:
        client = get_chroma()
        for col in client.list_collections():
            name = getattr(col, "name", col)
            if name.endswith(("_collection", "__sec_v1", "__sec_v2", "__ctx_v1")) and "broken" not in name:
                counts[name] = client.get_collection(name).count()
    except Exception as exc:          # recorded, not fatal
        counts = {"error": type(exc).__name__}
    return {"collections": counts, "embedding_model": retriever.MODEL_NAME,
            "embedding_version": result_cache.EMBEDDING_MODEL_VERSION,
            "chunking_version": result_cache.CHUNKING_STRATEGY_VERSION,
            "decision_policy_version": result_cache.DECISION_POLICY_VERSION}


def _settings_identity() -> dict:
    from app.core.config import settings
    from app.ai import response_policy
    keep = ("model", "embed", "rerank", "index", "llm", "provider", "retriev", "chat_")
    out = {k: v for k, v in sorted(settings.model_dump().items())
           if any(t in k.lower() for t in keep) and not any(b in k.lower() for b in _SECRET_HINTS)
           and (isinstance(v, (str, bool, int, float)) or v is None)}
    return {"effective_settings": out,
            "chat_adaptive_length_client": bool(settings.chat_adaptive_length_client),
            "response_policy_version": response_policy.POLICY_VERSION,
            "client_guard_version": getattr(response_policy, "CLIENT_GUARD_VERSION", None),
            "safety_guidance_version": _maybe("app.ai.imminent_danger", "GUIDANCE_VERSION"),
            "exact_provision_version": _maybe("app.ai.exact_provision", "INTEGRITY_VERSION")}


def _maybe(module: str, attr: str):
    try:
        import importlib
        return getattr(importlib.import_module(module), attr)
    except Exception:
        return None


class _SocketWS:
    def __init__(self, frame):
        self.script, self.sent = [frame], []

    async def accept(self):
        pass

    async def close(self, code=1000):
        self.closed = code

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_json(self):
        from app.websockets import chat_socket as cs
        if not self.script:
            raise cs.WebSocketDisconnect(1000)
        return self.script.pop(0)


def _compact_evidence(evidence: list[dict] | None) -> list[dict]:
    return [{"id": e.get("id"), "kind": e.get("kind"), "statute": e.get("statute"),
             "section": e.get("section"), "chunk_id": e.get("chunk_id"), "content": e.get("content", "")}
            for e in evidence or []]


async def _run_socket(items: list[dict], out: Path, label: str, pause: float) -> None:
    import datetime
    import logging
    _apply_overlay()
    from app.db.chroma import connect_chroma
    from app.db.collections import get_checkpoint_writes_col, get_checkpoints_col
    from app.db.mongodb import close_db, connect_db
    from app.ai import intent as intent_pkg
    from app.ai.graph.supervisor import chat_graph
    from app.services import provenance_outbox
    from app.websockets import chat_socket as cs
    import app.core.ws_ticket as ws_ticket
    sys.path.insert(0, str(BACKEND_DIR))
    from tests._conversation_fakes import FakeConversations, FakeTurns

    started = datetime.datetime.now(datetime.timezone.utc)
    await connect_db()
    connect_chroma()
    # The server warms these at startup (main._warmup_models), so a live first
    # question does not pay for them; without this the run's FIRST turn did
    # (c01 timed out at 145 s on 2026-10-14). Whisper is speech-only: skipped.
    from app.ai.corpus_index import get_index
    from app.ai.intent import warmup as intent_warmup
    from app.ai.pipelines.law_graph import get_graph
    from app.ai.pipelines.retriever import _embeddings
    await intent_warmup()
    for fn in (_embeddings, get_graph, get_index):
        await asyncio.to_thread(fn)
    manifest = {"label": label, "method": "socket-v1", "started_utc": started.isoformat(),
                "dataset": {"path": DATASET.relative_to(BACKEND_DIR).as_posix(),
                            "sha256": _sha256(DATASET.read_bytes()),
                            "items": len(items), "turns": sum(len(i["turns"]) for i in items)},
                "code": _code_identity(), "corpus": _corpus_identity(), **_settings_identity(),
                "env_overlay": ".env.analyzer-demo.local (values not recorded)",
                "server_warmup": "as main._warmup_models: intent, e5 embedder, law graph, corpus index "
                                 "(whisper skipped)"}

    # Count provider errors seen in logs without storing any message body.
    class _Counter(logging.Handler):
        def __init__(self):
            super().__init__(logging.WARNING)
            self.tool_use_failed = 0
            self.output_parse_failed = 0
            self.warnings = defaultdict(int)

        def emit(self, record):
            msg = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                msg += " " + str(record.exc_info[1])
            if "tool_use_failed" in msg:
                self.tool_use_failed += 1
            if "output_parse_failed" in msg:
                self.output_parse_failed += 1
            self.warnings[record.name] += 1
    counter = _Counter()
    logging.getLogger().addHandler(counter)

    captured: dict = {}

    async def ticket(_):
        return "eval-user"

    class _Users:
        async def find_one(self, q):
            return {"_id": "eval-user", "is_active": True, "role": "client"}

    async def record_outcome(**kw):
        captured["spans"] = kw.get("spans") or []
        return provenance_outbox.DURABLE, kw.get("request_id")

    real_classify = intent_pkg.classify

    async def classify(**kw):
        result = await real_classify(**kw)
        captured["intent"] = result.intent
        return result

    ws_ticket.consume_ticket = ticket
    cs.get_users_col = lambda: _Users()
    cs.provenance_service.record_outcome = record_outcome
    intent_pkg.classify = classify

    language_of = {"en": "en", "ur": "ur", "roman_ur": "en"}
    threads, failures = [], []
    try:
        with out.open("w", encoding="utf-8") as fh:
            for it in items:
                sid = f"{THREAD_PREFIX}{label}-{it['id']}-{uuid.uuid4().hex[:8]}"
                threads.append(sid)
                cs.conversations = FakeConversations(
                    session={"_id": f"doc-{sid}", "session_id": sid, "client_id": "eval-user", "messages": []},
                    owner_field="client_id")
                cs.turns = FakeTurns()
                for n, turn in enumerate(it["turns"], 1):
                    captured.clear()
                    frame = {"content": turn["q"], "language": language_of[it["lang"]], "province": "punjab",
                             "client_message_id": uuid.uuid4().hex}
                    ws = _SocketWS(frame)
                    t0 = time.perf_counter()
                    run_error = None
                    try:
                        await cs.chat_endpoint(ws, sid, ticket="eval")
                    except Exception as exc:          # recorded; the run continues
                        run_error = type(exc).__name__
                    ms = (time.perf_counter() - t0) * 1000
                    out_frames = [f for f in ws.sent if f.get("type") in ("final", "clarification", "error")]
                    f = out_frames[-1] if out_frames else {}
                    snap = await chat_graph.aget_state({"configurable": {"thread_id": sid}})
                    v = snap.values or {}
                    kind = f.get("type")
                    convergence = ("clarification" if kind == "clarification"
                                   else "error" if kind == "error" or run_error or not kind
                                   else f.get("convergence_status"))
                    answer = f.get("content") or f.get("question") or ""
                    generated = kind == "final" and bool(v.get("generation_evidence"))
                    spans = captured.get("spans") or []
                    llm = [{"model": s.get("name"), "status": s.get("status"), "error": s.get("error")}
                           for s in spans if s.get("kind") == "llm"]
                    node_errors = [s.get("name") for s in spans if s.get("kind") == "node"
                                   and s.get("status") == "error" and s.get("name") != "clarification_node"
                                   and s.get("name") != "fact_gap_node"]
                    row = {"label": label, "method": "socket-v1", "id": it["id"], "lang": it["lang"],
                           "category": it["category"], "turn": n, "query": turn["q"],
                           "intent": captured.get("intent", "resume"), "route": "socket",
                           "latency_ms": round(ms, 1), "answer": answer, "frame_type": kind,
                           "convergence": convergence,
                           "citations": f.get("citations") or [], "claims": f.get("claims") or [],
                           "is_grounded": v.get("is_grounded") if kind == "final" else None,
                           "response_mode": v.get("response_mode") if kind == "final" else None,
                           "followup_intent": v.get("followup_intent"), "case_type": v.get("case_type"),
                           "complexity": v.get("complexity"),
                           "evidence": _compact_evidence(v.get("generation_evidence")) if generated else [],
                           "llm_calls": llm, "node_errors": node_errors,
                           "safety_guidance": f.get("safety_guidance"),
                           "requested_provisions": v.get("requested_provisions") if kind == "final" else None,
                           "periods_removed": v.get("periods_removed") if kind == "final" else None,
                           "error": run_error or (f.get("message") if kind == "error" else None)}
                    if row["convergence"] == "error" or any(c["status"] == "error" for c in llm):
                        failures.append({"turn": f"{it['id']}.{n}", "frame": kind,
                                         "turn_failed": row["convergence"] == "error",
                                         "run_error": run_error,
                                         "llm_errors": [c["error"] for c in llm if c["status"] == "error"],
                                         "node_errors": node_errors})
                    fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    fh.flush()
                    print(f"{it['id']}.{n} {it['lang']:8} {row['intent']:13} {str(kind):13} "
                          f"{len(_words(answer)):4}w {ms / 1000:5.1f}s mode={row['response_mode']}", flush=True)
                    if pause:
                        await asyncio.sleep(pause)
    finally:
        intent_pkg.classify = real_classify
        for col in (get_checkpoints_col(), get_checkpoint_writes_col()):
            await col.delete_many({"thread_id": {"$in": threads}})
        await close_db()
        logging.getLogger().removeHandler(counter)
        finished = datetime.datetime.now(datetime.timezone.utc)
        manifest.update({"finished_utc": finished.isoformat(),
                         "duration_s": round((finished - started).total_seconds(), 1),
                         "failures": failures,
                         "turns_failed": sum(1 for f in failures if f["turn_failed"]),
                         "turns_recovered_after_provider_error": sum(1 for f in failures if not f["turn_failed"]),
                         "groq_tool_use_failed_log_lines": counter.tool_use_failed,
                         "groq_output_parse_failed_log_lines": counter.output_parse_failed,
                         "warning_log_counts": dict(counter.warnings),
                         "models_seen": sorted({c["model"] for r in [json.loads(l) for l in
                                                out.read_text(encoding="utf-8").splitlines() if l.strip()]
                                                for c in r.get("llm_calls", [])})})
        out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=1, default=str),
                                                     encoding="utf-8")


# ── assess ───────────────────────────────────────────────────────────────────

_DISCLAIMER_START = "*This information is for general guidance only"


def _body(text: str) -> str:
    text = text or ""
    i = text.find(_DISCLAIMER_START)
    return text[:i] if i >= 0 else text


def _words(text: str) -> list[str]:
    return re.findall(r"[\w؀-ۿ]+", _body(text))


def _sentences(text: str) -> list[str]:
    return [s.strip().lower() for s in re.split(r"[.!?۔\n]+", _body(text)) if len(s.split()) >= 5]


def _jaccard(a: str, b: str) -> float:
    x, y = set(a.split()), set(b.split())
    return len(x & y) / len(x | y) if x | y else 0.0


_DASHES = {**dict.fromkeys(map(ord, "‐‑‒–—−"), "-"),
           # no-break / narrow / thin spaces: models write "24 hours"
           **dict.fromkeys(map(ord, "    "), " ")}


def _norm(text: str) -> str:
    """Lowercase, every dash form as "-" (models write 489‑F with a
    non-breaking hyphen) and every no-break space as a space (a required
    "24 hours" written as "24 hours" was scored missing)."""
    return (text or "").translate(_DASHES).lower()


def _has(text: str, alternatives: list[str]) -> bool:
    low = _norm(text)
    return any(_norm(a) in low for a in alternatives)


_NEGATED = re.compile(r"not (?:included|provided|among|available|supplied|part of)|do(?:es)? not "
                      r"(?:contain|include|state|cover|set out|address)|cannot be (?:determined|established|"
                      r"confirmed|given)|could not be confirmed|is not (?:in|stated)|were not provided",
                      re.IGNORECASE)


def _raw_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?۔])\s+|\n+", _body(text)) if s.strip()]


def _false_passes(row: dict, spec: dict) -> list[str]:
    """Where the word-presence check says "present" but the answer does not
    actually deliver it. Each entry names the group and why.

      negated     -- the required term occurs only in sentences saying the
                     provision is NOT available / cannot be established;
      no_backing  -- a required SECTION is named, but no citation chip for it
                     was matched to the evidence the model saw;
      unsupported_period -- a required deadline is stated, but the period is
                     not stated for this matter by the evidence recorded for
                     the turn (ai/period_support.py);
      unverifiable_period -- as above, but the row carries no evidence (older
                     runs), so support cannot be checked.
    """
    from app.ai import period_support
    ans = row.get("answer") or ""
    sents = _raw_sentences(ans)
    out = []
    matched_sections = {_norm(str(c.get("section") or "")) for c in row.get("citations") or []
                        if c.get("status") == "matched"}
    for key in ("law", "deadline", "warning"):
        for group in spec.get(key, []):
            hits = [s for s in sents if _has(s, group)]
            if not hits:
                continue                                   # a plain miss, not a false pass
            if all(_NEGATED.search(s) for s in hits):
                out.append(f"{key}:{group[0]}:negated")
                continue
            if key == "law":
                # Only when the group is satisfied by SECTION numbers alone: an
                # Act name or a legal term in the group is not a citation.
                found = [a for a in group if any(_has(s, [a]) for s in hits)]
                is_section = [bool(re.fullmatch(r"\d{1,3}(?:\s?-?\s?[A-Za-z])?", _norm(a))) for a in found]
                if found and all(is_section) and not any(
                        _norm(a).replace(" ", "") in matched_sections for a in found):
                    out.append(f"law:{group[0]}:no_backing")
            if key == "deadline":
                evidence = row.get("evidence")
                period_hits = [s for s in hits if period_support.periods_in(s)]
                if not period_hits:
                    continue
                if not evidence:
                    out.append(f"deadline:{group[0]}:unverifiable_period")
                elif all(period_support.unsupported_periods(s, evidence) for s in period_hits):
                    out.append(f"deadline:{group[0]}:unsupported_period")
    return out


def _period_audit(row: dict) -> dict:
    """Periods stated in the visible answer, checked against the evidence the
    turn recorded. None when the row has no evidence (cannot be checked)."""
    from app.ai import period_support
    evidence = row.get("evidence")
    stated = [(s, p) for s in _raw_sentences(row.get("answer") or "")
              for p, _ in period_support.periods_in(s)]
    if not stated:
        return {"stated": 0, "unsupported": 0}
    if not evidence:
        return {"stated": len(stated), "unsupported": None}
    bad = sum(1 for s, p in stated if p in period_support.unsupported_periods(s, evidence))
    return {"stated": len(stated), "unsupported": bad}


def assess_turn(row: dict, spec: dict, prev_answer: str | None) -> dict:
    ans = row["answer"] or ""
    sents = _sentences(ans)
    dup = sum(1 for i, s in enumerate(sents) if any(_jaccard(s, t) >= 0.8 for t in sents[:i]))
    rep_prev = (sum(1 for s in sents if any(_jaccard(s, p) >= 0.8 for p in _sentences(prev_answer or "")))
                / len(sents)) if (prev_answer and sents) else None
    missing = [g for key in ("law", "deadline", "warning") for g in spec.get(key, []) if not _has(ans, g)]
    clarified = row.get("convergence") == "clarification" or "?" in _body(ans)[-300:]
    # The finalizer labels each chip: "matched" (cited and found in the evidence
    # the model saw), "unresolved" (cited, not in that evidence), "retrieved"
    # (shown, not cited). Only the first two are citations in the answer.
    cites = [c for c in (row.get("citations") or []) if c.get("status") in ("matched", "unresolved")
             or c.get("type") == "judgment"]
    unmatched = [c for c in cites if c.get("status") == "unresolved"]
    false_passes = _false_passes(row, spec)
    periods = _period_audit(row)
    visible_claims = [c for c in row.get("claims") or [] if not c.get("removed_from_answer")]
    complete = not missing and (clarified if spec.get("expect_clarification") else True)
    return {
        "false_passes": false_passes,
        "complete_strict": complete and not false_passes,
        "evidence_backed_citations": sum(1 for c in cites if c.get("status") == "matched"),
        "unsupported_claims": sum(1 for c in visible_claims if c.get("support") == "unsupported"),
        "periods_stated": periods["stated"], "periods_unsupported": periods["unsupported"],
        "deadline_supported": (None if not spec.get("deadline") else
                               all(_has(ans, g) for g in spec["deadline"])
                               and not any(f.startswith("deadline:") for f in false_passes)),
        "frame_type": row.get("frame_type"), "error": row.get("error"),
        "llm_errors": [c.get("error") for c in row.get("llm_calls") or [] if c.get("status") == "error"],
        "id": row["id"], "turn": row["turn"], "lang": row["lang"], "category": row["category"],
        "route": row.get("route"), "mode": row.get("response_mode"), "words": len(_words(ans)),
        "latency_ms": row["latency_ms"], "missing_required": missing,
        "complete": complete,
        "law_required": len(spec.get("law", [])),
        "deadline_kept": all(_has(ans, g) for g in spec.get("deadline", [])) if spec.get("deadline") else None,
        "warning_kept": all(_has(ans, g) for g in spec.get("warning", [])) if spec.get("warning") else None,
        "citations": len(cites), "citations_unmatched": len(unmatched),
        "is_grounded": row.get("is_grounded"),
        "repeated_sentences_within": dup, "repetition_vs_previous": rep_prev,
        "convergence": row.get("convergence"),
    }


def _pct(vals: list[float], p: float):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 1)


def summarise(turns: list[dict]) -> dict:
    def block(rows):
        return {"n": len(rows),
                "words_p50": _pct([r["words"] for r in rows], .5), "words_p95": _pct([r["words"] for r in rows], .95),
                "latency_ms_p50": _pct([r["latency_ms"] for r in rows], .5),
                "latency_ms_p95": _pct([r["latency_ms"] for r in rows], .95),
                "complete_rate": round(sum(r["complete"] for r in rows) / len(rows), 3) if rows else None,
                "complete_strict_rate": (round(sum(r["complete_strict"] for r in rows) / len(rows), 3)
                                         if rows else None),
                "false_passes": sum(len(r["false_passes"]) for r in rows),
                "clarifications": sum(1 for r in rows if r["convergence"] == "clarification"),
                "refusals": sum(1 for r in rows if r["convergence"] in ("max_attempts", "unanswerable")
                                and r["words"] <= 60),
                "errors": sum(1 for r in rows if r["convergence"] == "error"),
                "evidence_backed_citations": sum(r["evidence_backed_citations"] for r in rows),
                "unsupported_claims_visible": sum(r["unsupported_claims"] for r in rows),
                "periods_stated": sum(r["periods_stated"] for r in rows),
                "periods_unsupported": (None if any(r["periods_unsupported"] is None for r in rows)
                                        else sum(r["periods_unsupported"] for r in rows)),
                "deadline_supported": [r["deadline_supported"] for r in rows
                                       if r["deadline_supported"] is not None].count(True),
                "deadline_kept": [r["deadline_kept"] for r in rows if r["deadline_kept"] is not None].count(True),
                "deadline_total": sum(1 for r in rows if r["deadline_kept"] is not None),
                "warning_kept": [r["warning_kept"] for r in rows if r["warning_kept"] is not None].count(True),
                "warning_total": sum(1 for r in rows if r["warning_kept"] is not None),
                "citations_total": sum(r["citations"] for r in rows),
                "citations_unmatched": sum(r["citations_unmatched"] for r in rows),
                "zero_citation_answers": sum(1 for r in rows if r["citations"] == 0 and r["law_required"]),
                "repeated_sentences_within": sum(r["repeated_sentences_within"] for r in rows),
                "repetition_vs_previous_mean": (round(sum(r["repetition_vs_previous"] for r in rows
                                                          if r["repetition_vs_previous"] is not None)
                                                      / max(1, sum(1 for r in rows
                                                                   if r["repetition_vs_previous"] is not None)), 3)),
                }
    by_cat, by_lang = defaultdict(list), defaultdict(list)
    for r in turns:
        by_cat[r["category"]].append(r)
        by_lang[r["lang"]].append(r)
    return {"overall": block(turns), "by_category": {k: block(v) for k, v in sorted(by_cat.items())},
            "by_language": {k: block(v) for k, v in sorted(by_lang.items())},
            "incomplete": [f"{r['id']}.{r['turn']} missing {r['missing_required']}" for r in turns
                           if not r["complete"]],
            "false_passes": [f"{r['id']}.{r['turn']} {r['false_passes']}" for r in turns if r["false_passes"]]}


def assess(run_path: Path) -> dict:
    items = {it["id"]: it for it in load_items()}
    rows = [json.loads(l) for l in run_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    prev: dict[str, str] = {}
    turns = []
    for row in rows:
        spec = items[row["id"]]["turns"][row["turn"] - 1]
        turns.append(assess_turn(row, spec, prev.get(row["id"]) if row["turn"] > 1 else None))
        prev[row["id"]] = row["answer"]
    return {"run": str(run_path), "labels": "silver", "turns": turns, "summary": summarise(turns)}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--ids", default="")
    r.add_argument("--pause", type=float, default=8.0)
    r.add_argument("--method", choices=("socket", "thread"), default="socket",
                   help="socket = the real chat_endpoint (default); thread = the older per-turn-thread runner")
    a = sub.add_parser("assess")
    a.add_argument("--runs", required=True)
    a.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.cmd == "run":
        items = load_items()
        if args.ids:
            want = set(args.ids.split(","))
            items = [i for i in items if i["id"] in want]
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        runner = _run_socket if args.method == "socket" else _run
        asyncio.run(runner(items, Path(args.out), args.label, args.pause))
        return 0
    reports = {p: assess(Path(p)) for p in args.runs.split(",")}
    if args.out:
        Path(args.out).write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    for p, rep in reports.items():
        print("==", p)
        print(json.dumps(rep["summary"]["overall"], indent=1))
        for k, v in rep["summary"]["by_category"].items():
            print(f"  {k:12} n={v['n']} words p50={v['words_p50']} p95={v['words_p95']} complete={v['complete_rate']} "
                  f"lat p50={v['latency_ms_p50']}")
        print("  incomplete:", rep["summary"]["incomplete"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
