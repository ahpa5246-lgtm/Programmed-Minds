# Programmed Minds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Implement eight agents with evidence-preserving handoffs and original tool checks.
**Architecture:** Typed producer/critic pipeline, official SDK provider, fixed external CLI adapters, local artifact viewer.
**Tech Stack:** Python 3.11+, Pydantic 2, optional OpenAI SDK, unittest, original tool CLIs.
**Spec:** docs/superpowers/specs/2026-10-02-programmed-minds-design.md

## Global Constraints
No model-generated shell commands; no secrets in traces; required missing checks block; offline replay cannot pass release gates; research citations must occur in tool evidence; separate producer/critic identities when strict diversity is enabled.

## Review Focus
- Source URLs invented by the model must not count as researched evidence.
- A missing scanner or timeout must not become a pass.
- A critic approving with unresolved serious issues must stop the pipeline.
- Unsafe report paths, duplicate run directories, and untrusted HTML must be rejected or escaped.
- A tester report cannot override command failures or unexecuted UI tests.

### Task 1: Typed orchestration and inference
Files: programmed_minds/{models,provider,pipeline,cli}.py; tests/test_pipeline.py.
Interfaces: provider.generate(role, schema, context) -> dict with data, evidence_urls, identity, usage. run_pipeline(brief, provider, output_dir, max_revisions=2) -> manifest.
- [ ] Write fail-closed/revision/provenance tests and run them RED.
- [ ] Implement schemas, deterministic transitions, artifact hashes and SDK response parsing.
- [ ] Run tests GREEN and create a labelled replay example.

### Task 2: Tool checks
Files: programmed_minds/checks.py; tests/test_checks.py; integrations/.
Interfaces: run_checks(target: Path, config: dict, output: Path) -> report dict. report has status, checks; each check has name, status, required, argv, returncode, duration, log, reason. Status is passed/failed/error/missing/not_applicable; top-level passed or blocked.
- [ ] Write tests for missing tools, command failures, timeouts and URL/path safety; run RED.
- [ ] Implement real CLI command adapters and third-party integration templates.
- [ ] Run tests GREEN.

### Task 3: Local view and documentation
Files: programmed_minds/dashboard.py; README.md; examples/; tests/test_dashboard.py.
Interfaces: render_dashboard(run_dir: Path) -> str; serve(run_dir, host='127.0.0.1', port=8765).
- [ ] Write artifact escaping/RTL tests; run RED.
- [ ] Implement read-only responsive local viewer and usage documentation.
- [ ] Run full tests, offline scenario and CLI checks; review with a fresh reviewer.
- [ ] Fix consequential findings, record exact verification limits, and publish the tested implementation to the user's empty repository.
