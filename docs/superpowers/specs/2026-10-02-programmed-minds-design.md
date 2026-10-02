# Programmed Minds design

Build a reusable local Python application that runs eight named agents: researcher, research critic, improver, improvement critic, planner, plan critic, designer, and tester. This is the user's requested implementation in the empty Programmed-Minds repository.

## Intent and approaches
A prompt bundle alone cannot enforce execution. Reimplementing scanners loses their mature rules. The selected approach is a small orchestration application using the official OpenAI Python SDK for inference and original external CLIs for objective verification. No scanner source or rules are copied. AI reviews are advice; command exits and recorded artifacts determine verification status.

## Workflow
Research and critique -> improve and critique -> plan and critique -> design -> handoff to an existing coding agent -> run original verification tools -> tester audit. Producers receive objections and have at most two revisions. A rejection or unresolved serious objection stops progression. Each response is validated with a stage-specific Pydantic schema. Each stage writes immutable JSON containing input/output hashes, model identity, tokens, and evidence. Research/design sources must have URLs observed in live search output; this proves provenance, not truth. Novelty and competition victories require sources, not unsupported claims. A supplied brief contains competition rules and user needs; rule links can be investigated by research.

## Independence and boundaries
Critics can use separate endpoints and models. Strict diversity checks producer/critic endpoint+model identity, without claiming statistical independence. Model text never becomes a shell command. The system emits a detailed coding handoff rather than claiming the planning agents edited the target. The user runs their coding agent against it. A CLI can then inspect a real trusted target repository using a fixed tool allowlist. Repository test scripts are executable code: only run checks in repositories the user trusts.

## External integrations
Superpowers is used by the coding handoff via its original installation. PR-Agent/Qodo has a sample config and optional workflow requiring model credentials. ASVS 5.0 is a referenced manual standard with evidence mapping, never a pretend scanner. Semgrep, Gitleaks, OSV-Scanner, Trivy, ZAP, pgTAP, Playwright, Lighthouse CI, Size Limit, and k6 use their real CLIs. Applicable checks explicitly report passed, failed, error, missing, or not applicable. Required missing checks fail closed. Reports contain fixed argv, exit status, elapsed time, sanitized log paths and report hash. Load/HTTP checks require explicit owned target URLs. ZAP baseline is default; no implicit active attack.

## Interface and constraints
Python >=3.11; offline core tests use unittest; optional live OpenAI SDK dependency; no keys in config or traces. JSON config uses environment-variable names. Offline replay is labelled demo and cannot produce release approval. A local read-only RTL dashboard views artifacts and tool reports. Output directories cannot silently overwrite earlier runs. Run artifacts are ignored by git. Target commands have timeouts and no shell execution. No arbitrary paths supplied by model outputs are used for filesystem mutations. Search is limited to research and design. There is a maximum model-call budget and token ceiling. Test audit is supplied actual tool results, and cannot override failed or missing checks.

## Acceptance
Offline complete flow, bounded revisions and stop behavior, diversity policy, malformed outputs, missing tools, nonzero exits, timeouts, path safety, command injection resistance, target URL handling, audit fail-closed behavior, and dashboard injection protection are covered by meaningful tests. Live model calls and installed scanners must be distinguished from fixture tests. No commercial-readiness claim without their real evidence.
