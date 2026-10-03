# Codex-led research, improvement and planning

Use this workflow when the user asks Codex to act as the three principal agents in conversation. This is a project instruction for Codex, not an installed copy or execution of BMad, gstack, Spec Kit or Superpowers. Invoke original installed skills when available and relevant; their own instructions take precedence over this summary. Never claim a named upstream skill ran when it did not.

## Evidence ledger and decision rule

Start with the actual user's goal and official competition rules. Search the official pages and timestamp the rules, eligibility, judging rubric, submission requirements, deadlines and permitted technologies. Record source URL, claim, direct support, date, uncertainty and how to falsify it. A page being visited does not establish that it supports every claim. Explicitly separate fact, inference and hypothesis. If official rules are not accessible, stop the competition-specific decision and request the missing rule text. Never infer actual rival entries or guarantee a prize.

For each stage save an artifact under `runs/codex/<run-id>/` with the brief, citations, unresolved questions, alternatives considered, critic report and decision. No secret keys or private source content in committed artifacts. Codex's own conversation model handles principal roles; no `OPENAI_API_KEY` or model identity can be selected by this repository.

## 1. Researcher — decision research (BMad deep-recon, forge-idea)

Investigate at least three candidate directions where evidence allows. For each: target user and costly problem; comparable products or winners with official proof; specific edge for this contest; scope within time and budget; weakest assumption; disconfirming experiment. Pressure-test novelty, technical feasibility and whether the mandated platform is essential to the demo. Search for contrary evidence deliberately. A prior winner shows what was rewarded then, not what will win now. Deliver a ranked shortlist with source-linked facts and a reason to discard each losing candidate. If evidence is thin, say so and narrow claims.

## 2. Improver — product and rival challenge (gstack office-hours/CEO review, BMad prfaq)

Do not agree with the user's proposed solution automatically. Restate the user problem, strongest plausible rival, how judges will actually observe the advantage, and a concrete way the chosen project loses. Compare the chosen idea to at least one simpler alternative and the strongest plausible competitor. Remove features that do not improve the demonstration. State changes with cost, benefit and measurable acceptance. Run a small experiment that could overturn the recommendation before committing to build. Make an explicit `go`, `clarify` or `stop` decision: `go` requires verified critical rules and a falsifiable advantage; `clarify` lists questions that can change the choice; `stop` gives evidence for abandonment. A critic approval alone cannot turn `clarify` into `go`.

## 3. Planner — specification and engineering (Spec Kit assess/clarify/analyze, gstack eng review)

Translate the surviving concept into requirements with stable IDs, an acceptance criterion and an actual test for each. Map judging criteria to observable demo steps and evidence. Specify architecture, data and schema, auth/permissions if needed, UI states, failure recovery, accessibility, deployment, rollback and scope cuts. Name repository paths, task dependencies and test IDs. Decide applicability of each tool listed in `programmed_minds/models.py::TOOLS`, with reason and real evidence expected. Include a task to resolve each remaining unknown and a scenario where an apparently functioning implementation still loses on judging criteria. Never mark scanners, browser flows, user testing or code review passed from a planned command.

## Critics and execution

After each principal artifact, call `python -m programmed_minds critique` with the appropriate role, an actual JSON draft, the brief and the two-key config. The critic must cite precise weaknesses, give a verdict and ask disconfirming questions. Read and answer objections with new evidence; unresolved medium or higher issues block the next stage. Save critic JSON and the revised principal artifact. The API models are outside reviewers, not proof of correctness; their free quotas and model availability are outside this repository's control.

When all three stages pass, prepare `HANDOFF.md` and implement in the trusted product repository using original installed Superpowers skills. Run the original security, database, UI and performance tools only where applicable. Do not imply this planning repository wrote, deployed or tested the product unless those operations actually happened.

Upstream references: [BMad](https://github.com/bmad-code-org/BMAD-METHOD), [gstack](https://github.com/garrytan/gstack), [Spec Kit](https://github.com/github/spec-kit), [Superpowers](https://github.com/obra/superpowers).
