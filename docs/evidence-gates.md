# Competition evidence gates

Programmed Minds now treats a model's `go` as an opinion, not release evidence. Live `pminds plan` runs for named competitions will **not emit a coding handoff** until the mandatory handoff evidence is present and hash-bound to the exact brief. Offline replay is still a demonstration and is never release approval.

## Gate stages and required records

| Stage | Required check IDs | What it means |
| --- | --- | --- |
| `handoff` | `rules_review`, `competitor_comparison`, `falsification_spike` | Official rules reviewed; alternatives or rivals actually compared; at least one disconfirming experiment attempted and documented |
| `release` | `holdout_benchmark`, `outside_user_study`, `live_ai_probe`, `end_to_end_demo` | Measured holdout study, independent user sessions, actual live model interaction, and a complete user journey documented for the exact Git commit |

Each artifact must be a **real, nonempty file** under the evidence manifest directory. The gate checks SHA-256, file size, duplicate IDs, path escape/symlinks, `passed` status, method and positive sample count. A report saying `blocked` or `not_run` fails closed. A modified artifact, edited brief, or changed/dirty release checkout fails closed. There is no network access, inference or external command execution from evidence files.

These checks prove **traceability, not scientific validity**. Someone can still fabricate a document and its digest; the operator/reviewer must inspect source data, sampling, methodology and claims. Never label `evidence_documented` as a prize prediction, a safety certificate or production readiness.

## Prepare the manifest

Save your official competition brief as `brief.json`. Compute its fingerprint using the same canonical encoding as the pipeline:

```bash
python -c "import json; from programmed_minds.evidence_gates import fingerprint; print(fingerprint(json.load(open('brief.json',encoding='utf-8'))))"
```

Create `evidence/handoff.json`:

```json
{
  "version": 1,
  "stage": "handoff",
  "brief_sha256": "REPLACE_WITH_64_CHARACTER_BRIEF_DIGEST",
  "checks": [
    {
      "id": "rules_review",
      "status": "passed",
      "method": "Manually compared the official published rules to our scope",
      "sample_count": 1,
      "artifact": "rules-review.md",
      "sha256": "REPLACE_WITH_SHA256_OF_RULES_REVIEW_FILE"
    },
    {
      "id": "competitor_comparison",
      "status": "passed",
      "method": "Replicated two comparable public demo flows",
      "sample_count": 2,
      "artifact": "competitors.md",
      "sha256": "REPLACE_WITH_SHA256_OF_COMPETITORS_FILE"
    },
    {
      "id": "falsification_spike",
      "status": "passed",
      "method": "Executed one test that could disprove the project's differentiation",
      "sample_count": 1,
      "artifact": "spike-results.json",
      "sha256": "REPLACE_WITH_SHA256_OF_SPIKE_FILE"
    }
  ]
}
```

A successful `status` must mean the corresponding action was actually performed and its outcomes are in the attached file, including failures. For SHA-256 use `python -c "import hashlib; print(hashlib.sha256(open('evidence/rules-review.md','rb').read()).hexdigest())"`, then repeat for each file. Do not mark a planned test as `passed`.

The full automated route:

```bash
pminds plan --brief brief.json --config examples/fully-free.json --evidence evidence/handoff.json --out runs/competition-01
```

With no evidence, a live competition run may produce research/critic artifacts for investigation, but cannot produce `HANDOFF.md`. Fix the objection or attach actual evidence and run again with a fresh output directory.

## The Codex-led route must close all three critiques

Codex may draft the research, improvement and plan JSON files. Use `pminds critique` for each role and keep its `review.json` output. Create `evidence/codex-reviews.json` with relative paths to the *same exact drafts*:

```json
{
  "version": 1,
  "reviews": {
    "research_critic": {
      "draft": "research.json",
      "review": "research-review/review.json"
    },
    "improvement_critic": {
      "draft": "improvement.json",
      "review": "improvement-review/review.json"
    },
    "plan_critic": {
      "draft": "plan.json",
      "review": "plan-review/review.json"
    }
  }
}
```

Paths resolve relative to `codex-reviews.json`. All three critiques must be approved, have no medium/high/critical issues, and match the exact submitted draft and brief hashes. If Codex rewrites a draft, its previous review becomes stale and must be rerun. Running one critic three times does not independently prove correctness; check the model identities and evidence yourself.

```bash
pminds gate --stage handoff --brief brief.json --evidence evidence/handoff.json --codex-manifest evidence/codex-reviews.json
```

Do **not** send code to an implementation agent if this command exits nonzero. The separate `pminds plan` route already enforces its own internal three critiques.

## Release readiness after implementing the project

Run the actual target tests and `pminds audit` first. For `release`, create another manifest with `stage: "release"`, the four release check IDs, and `target_commit` equal to `git rev-parse HEAD` of the **clean Git checkout**. Store evidence outside the target repository, or commit it before computing the target hash. Include concrete measured outputs, not just narrative promises.

```bash
pminds gate --stage release --brief brief.json --evidence evidence/release.json --target /path/to/target-repo --audit-manifest runs/audit-01/manifest.json
```

Release fails if the checkout is dirty or points to a different commit, any evidence is missing/stale, or the post-build audit has not returned `verified` **for that same target commit**. The tool-check report records the clean commit before and after checks and blocks if those revisions differ; non-Git and dirty targets can still run checks, but cannot pass release readiness. Even when the command returns `evidence_documented`, the existing audit's `release_approved: false` remains in force: a human must inspect the outcomes and authorize release. GitHub branch protection or a required CI job must call the gate from the target repository to make it a technical merge barrier; the CLI cannot stop someone bypassing the workflow on Devpost or pushing directly to an unprotected branch.

## Security and limitations

The evidence directory and Git checkout are **trusted local inputs**, not a tamper-proof witness. The hashes prevent accidental drift and routine stale approvals, not a malicious operator from rewriting both artifact and manifest. There is no universal automated test for novelty, user impact, or whether participants were truly independent. For scientific or high-stakes claims, demand external reviewers and stronger provenance/signatures before changing the status. Avoid personally identifying user-study data and API credentials in published evidence.
