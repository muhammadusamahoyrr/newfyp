# Claim-check pilot -- run log

| run | date | calls | outcome | labels |
|---|---|---|---|---|
| 1 | 2026-10-15 | 23 sent (approved; synthetic, privacy-checked 0 PII / 0 source runs; groq3 gpt-oss-120b pinned, no failover, no retry) | **23 x BadRequestError (HTTP 400)**, no output; error text not recorded (script kept only the type -- fixed after the run) | no independent labels -> would have been exploratory only |

No measurement exists. Fact fidelity remains OPEN; nothing is wired into Insert. A diagnostic call to read the 400
message needs separate approval. Results: `results.run1_all_400.jsonl`.

## Local inspection of the HTTP 400 (2026-10-15, no provider call)
* Request built locally (dummy key) and its exact HTTP body captured with a mock transport: system + user messages,
  model `openai/gpt-oss-120b`, n 1, temperature 0.1, max_tokens 2000, service_tier on_demand; `reasoning_format`,
  `reasoning_effort` and `stop` sent as null. IDENTICAL to the drafter's streaming request (only `stream` differs),
  and the drafter's groq5 calls succeeded in v2_r3.
* All five Groq accounts are configured (checked as booleans; no key value read out). groq3 + gpt-oss-120b succeeded
  on 2026-10-13 (legal_rag closure results), but only for STRUCTURED intake calls; no 400 is on record locally.
* Conclusion: nothing in the request format or model settings explains the 400 locally. The remaining differences are
  server-side -- the groq3 account, and a plain non-streaming call. Only the provider's error text can settle it; the
  script now records it (redacted). A single diagnostic call needs separate approval.
