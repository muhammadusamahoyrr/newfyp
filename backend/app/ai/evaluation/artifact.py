"""Evaluation artifact provenance (2026-10-13 closure patch).

A result is only evidence about the code that produced it. Earlier stability
reports mixed runs from different source states and one saved "final" report
predated the final guard. Every generation record now carries a provenance
block, and runs are combined ONLY when their source fingerprint, dataset hash
and evaluator contract match.

Never recorded: API keys, environment variables, `.env` (not fingerprinted),
provider error text. Provider events use provider_health's fixed vocabulary
(provider, model, tier, purpose, outcome, kind, status_code).
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
EVALUATOR_VERSION = "generation-eval-v3"   # provision-level + visible-mismatch + stability dimensions

# The files whose content decides what an intake analysis looks like and how
# it is judged. `.env` is deliberately absent.
PIPELINE_FILES = (
    "app/ai/llm.py", "app/core/config.py",
    "app/ai/nodes/retrieval_node.py", "app/ai/nodes/retrieval_grader_node.py",
    "app/ai/nodes/intake_evidence_gate_node.py", "app/ai/nodes/intake_node.py",
    "app/ai/nodes/intake_hallucination_node.py", "app/ai/nodes/intake_finalizer_node.py",
    "app/ai/graph/supervisor.py", "app/ai/intake_evidence.py", "app/ai/intake_output_guard.py",
    "app/ai/intake_localization.py", "app/ai/legal_terms.py", "app/ai/intake_understanding.py",
    "app/ai/fact_fidelity.py", "app/ai/section_repair.py", "app/ai/pipelines/retriever.py",
    "app/services/intake_service.py", "app/ai/evaluation/legal_rag.py", "app/ai/evaluation/artifact.py",
    "scripts/eval_generation.py", "scripts/eval_stability.py",
)
_SAFE_EVENT_KEYS = ("provider", "model", "tier", "purpose", "outcome", "kind", "status_code", "is_fallback")


def source_fingerprint(files=PIPELINE_FILES, root: Path = BACKEND_DIR) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        p = root / rel
        h.update(rel.encode())
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()[:16]


def file_hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=BACKEND_DIR, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def run_header(dataset_paths: list[str]) -> dict:
    """Code/config identity of a generation run. No secrets."""
    from app.ai.intake_output_guard import GUARD_VERSION
    from app.ai.nodes.intake_evidence_gate_node import GATE_VERSION
    from app.core.config import settings
    return {
        "git_commit": _git("rev-parse", "HEAD")[:12],
        "worktree_dirty": bool(_git("status", "--porcelain", "--", ".")),
        "source_fingerprint": source_fingerprint(),
        "datasets": {str(p): file_hash(BACKEND_DIR / p) for p in dataset_paths},
        "evaluator_version": EVALUATOR_VERSION,
        "gate_version": GATE_VERSION,
        "output_guard_version": GUARD_VERSION,
        "index_variant": settings.retrieval_index_variant,
        "multi_query": settings.retrieval_multi_query,
        "agentic": settings.agentic_decomposition_enabled,
    }


def safe_events(events: list[dict]) -> list[dict]:
    return [{k: e.get(k) for k in _SAFE_EVENT_KEYS if k in e} for e in events or []]


def run_record(header: dict, events: list[dict], *, pipeline_failed: bool, language: str) -> dict:
    ev = safe_events(events)
    return {**header,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "effective_language": language,
            "provider_events": ev,
            "providers_used": sorted({f"{e['provider']}/{e['model']}" for e in ev if e.get("outcome") == "success"}),
            "provider_limit_hit": any(e.get("kind") in ("rate_limit", "payment_required") or
                                      e.get("status_code") in (402, 429) for e in ev),
            "pipeline_failed": pipeline_failed}


def contract(record: dict) -> tuple:
    p = record.get("provenance") or {}
    return (p.get("source_fingerprint"), tuple(sorted((p.get("datasets") or {}).items())),
            p.get("evaluator_version"))


def combinable(records: list[dict]) -> tuple[bool, str]:
    """May these generation records be reported together?"""
    if any("provenance" not in r for r in records):
        return False, "a record carries no provenance (produced before provenance was recorded)"
    contracts = {contract(r) for r in records}
    if len(contracts) != 1:
        return False, f"{len(contracts)} different source/dataset/evaluator contracts"
    return True, "one contract"
