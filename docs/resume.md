# Resume after a provider interruption

```bash
pminds plan --brief PRIVATE-brief.json --config PRIVATE-models.json --resume-from PRIVATE-interrupted-run --out PRIVATE-resumed-run
```

Always choose a fresh output directory. The original run is read only and retains every trace. The resumed run records its source and marks reused stage entries.

Each successful stage writes an immutable progress snapshot. A normal blocked run resumes from its manifest; an interrupted process without a final manifest resumes from its latest complete snapshot. Stages are reused in order only when their role, output digest and reconstructed input digest match. The current schemas and domain checks run again. Changing the brief, live/demo mode, revision policy or diversity policy blocks reuse.

Mandatory competition evidence is checked again before any model call and at handoff, including during resume. A resumed model review remains advisory and cannot approve a release. Digests detect edits; they do not authenticate the original author.

For offline replay experiments, supply responses for the unfinished calls; production providers do not need the completed calls again. Call budgets apply per invocation; no automatic retries or background worker is installed.
