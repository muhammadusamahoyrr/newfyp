"""Is a versioned identity index present AND the one we verified? (2026-10-16)

The lawyer drafter and lawyer research read the versioned identity indexes:
criminal `__sec_v2` (lettered sections relabelled) and civil `__ident_v2` (CPC
Order/Rule and Limitation Schedule/Article identities). Until now a missing
identity index was replaced, silently, by the BASE collection -- whose CPC
labels are the ones the identity build exists to repair ("Section 17 CPC"
resolving to Order XI Rule 17). The output then looked identity-checked when it
was not.

This module answers one question per collection -- may it be used as THE
identity index? -- from what the build reports recorded, never from a guess:

  missing      the collection does not exist
  unreadable   it exists but could not be counted / read (damaged or locked)
  unverified   it reads, but is not the build we verified: wrong build marker
               or a different chunk count (any rebuild must update the pins
               below, deliberately, with its own report)
  ok

What it cannot see: damage inside the HNSW vector files that a count and a
one-row read do not touch. That needs the snapshot procedure
(evals/legal_sources/BATCH2_PARSER_STATUS_INDEX.md §7), not a request-time
check.

Callers that need an identity index raise `IdentityIndexUnavailable` (a
`CorpusUnavailable`, so every existing fail-closed path already handles it).
Client chat and intake never call this: their retrieval policy is unchanged.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from app.ai.exact_provision import CorpusUnavailable

logger = logging.getLogger(__name__)

# What the build reports recorded. A deliberate rebuild updates these together
# with its report; nothing else may.
EXPECTED: dict[str, dict] = {
    # evals/legal_rag/results/sec_index_audit_2026-10-13.json (id_fingerprint 24848d530b2d2559)
    "criminal_collection__sec_v2": {"count": 3305, "metadata": {"sec_schema": "sec-v2",
                                                                "split_version": "section-split-v2"}},
    # evals/drafter_v2/ident_v2_dryrun/build_checks.v3.json (post_checks_passed: true)
    "civil_collection__ident_v2": {"count": 4648, "metadata": {"ident_version": "ident-v2",
                                                               "build_run_id": "646c85cde01548758dc06f97f8938b86"}},
}
# base collection -> the identity index the drafter and research require
IDENTITY_FOR = {"criminal_collection": "criminal_collection__sec_v2",
                "civil_collection": "civil_collection__ident_v2"}

_TTL_SECONDS = 300          # a healthy result
_TTL_FAILED_SECONDS = 30    # a failure is re-checked soon after a fix


@dataclass(frozen=True)
class Health:
    collection: str
    status: str            # ok | missing | unreadable | unverified
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class IdentityIndexUnavailable(CorpusUnavailable):
    """A required identity index is missing, unreadable or not the verified
    build. Carries no document or answer text."""

    def __init__(self, health: Health):
        super().__init__(f"identity index {health.collection} {health.status}")
        self.health = health

    def as_dict(self) -> dict:
        return {"status": "identity_index_unavailable", "collection": self.health.collection,
                "problem": self.health.status}


_cache: dict[str, tuple[float, Health]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def check(name: str, client=None) -> Health:
    """Health of one identity collection (cached for a few minutes)."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(name)
        if hit and now - hit[0] < (_TTL_SECONDS if hit[1].ok else _TTL_FAILED_SECONDS):
            return hit[1]
    health = _check_uncached(name, client)
    if not health.ok:
        logger.error("index_health: %s is %s (%s)", name, health.status, health.detail)
    with _lock:
        _cache[name] = (now, health)
    return health


def _check_uncached(name: str, client) -> Health:
    expected = EXPECTED.get(name)
    if expected is None:
        return Health(name, "unverified", "no recorded build to compare with")
    try:
        if client is None:
            from app.db.chroma import get_chroma
            client = get_chroma()
        col = client.get_collection(name)
    except Exception as exc:  # noqa: BLE001 -- chromadb raises several types for "not found"
        text = str(exc).lower()
        status = "missing" if ("does not exist" in text or "not found" in text or "notfound" in
                               type(exc).__name__.lower()) else "unreadable"
        return Health(name, status, type(exc).__name__)
    try:
        count = col.count()
        col.get(limit=1, include=["metadatas"])          # one row actually reads
        meta = dict(col.metadata or {})
    except Exception as exc:  # noqa: BLE001
        return Health(name, "unreadable", type(exc).__name__)
    wrong = [k for k, v in expected["metadata"].items() if meta.get(k) != v]
    if wrong:
        return Health(name, "unverified", f"build marker mismatch: {', '.join(sorted(wrong))}")
    if count != expected["count"]:
        return Health(name, "unverified", f"{count} chunks, verified build had {expected['count']}")
    return Health(name, "ok")


def require(name: str, client=None) -> str:
    """The collection name, or IdentityIndexUnavailable."""
    health = check(name, client)
    if not health.ok:
        raise IdentityIndexUnavailable(health)
    return name


def require_all(names, client=None) -> list[str]:
    return [require(n, client) for n in names]


def require_readable(name: str, client=None) -> str:
    """A collection with NO identity build (family, constitutional): it must
    exist and read, nothing more -- there is no recorded build to compare it
    with, so demanding one refused every request (2026-10-19)."""
    try:
        if client is None:
            from app.db.chroma import get_chroma
            client = get_chroma()
        col = client.get_collection(name)
    except Exception as exc:  # noqa: BLE001 -- chromadb raises several types for "not found"
        text = str(exc).lower()
        status = "missing" if ("does not exist" in text or "not found" in text or "notfound" in
                               type(exc).__name__.lower()) else "unreadable"
        raise IdentityIndexUnavailable(Health(name, status, type(exc).__name__))
    try:
        col.count()
        col.get(limit=1, include=["metadatas"])
    except Exception as exc:  # noqa: BLE001
        raise IdentityIndexUnavailable(Health(name, "unreadable", type(exc).__name__))
    return name


def require_drafter(names, client=None) -> list[str]:
    """The drafter's collections: an identity build must be the VERIFIED one;
    a collection that has none must exist and read."""
    return [require(n, client) if n in EXPECTED else require_readable(n, client) for n in names]
