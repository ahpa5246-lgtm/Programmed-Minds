# Verification record

## Local evidence, 2026-10-02

- `python -m unittest discover -s tests -v`: 64 tests passed, zero failures. Includes actual Python subprocess execution, process timeout termination, localhost HTTP requests and audit log validation; external scanner calls and inference are mocked where unavailable.
- CLI offline `plan` ran through researcher, three critics, improver, planner and designer, producing immutable stage records and HANDOFF.md. Tester executes in the separate post-implementation audit. Fixture sources are demonstration material, not real research.
- Wheel build succeeded via `python -m pip wheel . --no-deps --no-build-isolation`; packaged project-owned Semgrep rule confirmed present.
- Real check-policy invocation correctly reports blocked with missing Semgrep/Gitleaks/OSV/Trivy rather than pretending they passed. Unit tests execute; tool installation is a separate prerequisite.
- Playwright browser launch was attempted but Chromium is not installed in this environment. No browser screenshot, visual QA or live user interaction is claimed. Dashboard HTTP and escaping tests passed.
- No live model API requests were made; no key or inference service was supplied. Official SDK request shape, structured output, budget, missing evidence and error redaction tested with a fake client.

## Independent review and fixes

A fresh reviewer identified scanner-only functional acceptance, Unicode report hashes, output ancestor symlinks and separate-root dashboard integration. Regression tests reproduced the first three and split-root viewer tests reproduced the fourth before fixes.

Functional acceptance now requires the configured appropriate test engine, an exact executed test ID, one unambiguous passed result, a matching report/log hash, and the real contained log file. Scanner status alone cannot cover a functional requirement. Arabic paths and report content round-trip with a consistent canonical JSON hash. Planning/audit reject output ancestor symlinks. Viewer roots are explicit user inputs; raw manifest references never authorize cross-root reads.

The process runner is POSIX-specific. Linux/macOS/WSL are required for external checks; the CLI rejects other platforms before starting checks. This avoids pretending Windows process-group termination is supported. Planning/viewing do not need this runner.

## CI and limits

Active `.github/workflows/ci.yml` calls original Semgrep, Gitleaks, OSV-Scanner and Trivy. Versions of GitHub Actions are pinned to official retrieved commit IDs. Writing the workflow is not proof its scans passed: inspect GitHub Actions for actual results. Branch protection must be configured in repository settings if these statuses must block merges.

Qodo/PR-Agent remains opt-in because it needs provider credentials and an explicit review deployment. ASVS is a manual standard, not a scanner; evidence mapping remains unassessed until the actual target is implemented and reviewed. pgTAP needs a real PostgreSQL test database. Browser/performance/load examples require project-specific tests, an owned running target, installed tools and meaningful budgets. Example selectors/assertions do not test an unknown application.

Hashes detect changes but are not cryptographic signatures proving provenance against a malicious local operator. The target and configuration are trusted inputs. No universal claim of perfect security, commercial readiness, novel ideas, independent model errors or clicking every possible UI state is made.

## Observed GitHub Actions execution

The first published code commit `5fa06fe8e71fb1b40e8fba75f9ce56133d65617a` completed all four jobs successfully in [run 37057805096](https://github.com/ahpa5246-lgtm/Programmed-Minds/actions/runs/37057805096):

- Core tests: 64 passed. Semgrep: the three project-owned rules ran on nine Python files with zero findings. This is a narrow rule set, not comprehensive SAST coverage.
- Gitleaks: original action completed successfully against repository history.
- OSV-Scanner: original scanner and reporter completed successfully, with no issues reported for the scanned dependency inputs. The locked requirements cover the core runtime; optional live SDK dependencies need their own resolved lockfile when deployed.
- Trivy: filesystem scan completed successfully; requirements.txt had zero findings at the configured HIGH/CRITICAL threshold. No infrastructure config files were detected, and license detection was skipped because site-packages was absent. These unscanned areas are not claimed clean.

The CLI remains blocked locally when the original binaries are not installed. CI evidence applies to this repository snapshot; it does not certify an unbuilt target project, live inference correctness, all ASVS controls, browser interaction, or future vulnerability databases.
