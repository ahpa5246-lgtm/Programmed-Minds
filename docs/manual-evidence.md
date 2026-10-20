# Recorded manual review evidence

Run original checks against a clean target revision first. Then supply an owner-reviewed JSON manifest to:

```bash
pminds audit --run PRIVATE-plan --checks PRIVATE-checks/checks.json --manual-evidence PRIVATE-reviews/manual.json --config PRIVATE-models.json --out PRIVATE-audit
```

The manifest has `version: 1`, `approved_sha256` (the pipeline's `digest(approved.json)`), `target_commit` matching the checks report, and two arrays:

- `requirements`: one record for every requirement whose `evidence_tool` is `manual`, with `requirement_id` and its exact planned `test_id`.
- `gates`: one record for every applicable required `asvs`, `qodo`, or `superpowers` gate, identified by `tool`.

Each record needs `status: "passed"`, nonempty `reviewer` and `method`, an ISO `reviewed_at` timestamp with timezone, a relative `artifact` path within the manifest directory, and the artifact's `sha256`. Unknown, duplicate, missing, failed, stale or changed reviews block the audit. Symlinks and parent-directory escapes are rejected.

The actual review must describe observations, requirements inspected, negative cases and unresolved limitations. A scanner report cannot substitute for a human assessment. Keep personal review records and source evidence outside public Git.

A passing audit validates traceability to recorded attestations and executed checks. It cannot authenticate a reviewer, prove independence or certify the conclusions. It always leaves `release_approved` false; release requires a separate human decision.

Competition planning now checks mandatory evidence before the first model call and again before writing the coding handoff. Missing or stale evidence no longer consumes a sequence of model calls first.
