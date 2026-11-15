# Superseded diffs -- DO NOT APPLY

Kept only as an audit trail. The build script accepts a diff only with a matching `.lock.json`; these have none.

| File | Changes | Why superseded |
|---|---|---|
| `ident_v2_metadata_diff.json/.md` (+ `build_checks.json`) | 272 | Pre-checks failed on 30 chunks: the dry run placed a chunk's END at start + length in the official text; inline footnotes made it overshoot into the next rule, adding rules the chunk does not hold. |
| `ident_v2_metadata_diff.v2.json/.md` (+ `build_checks.v2.json`) | 237 | Positions from body text only; 4 chunks still failed (the official text puts the next rule in the chunk, the local copy shows no heading for it). |

Current: `ident_v2_metadata_diff.v3.json` (233 changes, sha256 in `ident_v2_metadata_diff.v3.lock.json`).
