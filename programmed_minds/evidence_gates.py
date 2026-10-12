"""Fail-closed, file-backed evidence gates; model opinions never substitute for evidence.

The gate verifies traceability and freshness, not the scientific validity of a study.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

REQUIRED = {
    "handoff": ("rules_review", "competitor_comparison", "falsification_spike"),
    "release": ("holdout_benchmark", "outside_user_study", "live_ai_probe", "end_to_end_demo"),
}
MIN_SAMPLES = {"competitor_comparison": 2, "holdout_benchmark": 10, "outside_user_study": 2}
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HEX_GIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_ARTIFACT_BYTES = 2_000_000


class EvidenceError(ValueError):
    """An evidence gate cannot authorize the next transition."""


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _file_bytes(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise EvidenceError("Evidence artifact path must be a relative POSIX path")
    path = Path(relative)
    if path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise EvidenceError("Evidence artifact path escapes evidence directory")
    resolved = root.joinpath(path)
    if any(part.is_symlink() for part in (resolved, *resolved.parents) if part != root.parent):
        raise EvidenceError("Symlinked evidence paths are not allowed")
    if not resolved.resolve().is_relative_to(root.resolve()) or not resolved.is_file():
        raise EvidenceError("Missing or unsafe evidence artifact: " + relative)
    size = resolved.stat().st_size
    if not 1 <= size <= MAX_ARTIFACT_BYTES:
        raise EvidenceError("Evidence artifact empty or too large: " + relative)
    return resolved.read_bytes()


def _git_commit(target):
    root = Path(target).resolve(strict=True)
    commands = (("rev-parse", "--show-toplevel"), ("rev-parse", "HEAD"),
                ("status", "--porcelain", "--untracked-files=all"))
    values = []
    for parts in commands:
        result = subprocess.run(["git", "-C", str(root), *parts], check=False,
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise EvidenceError("Cannot inspect target Git repository")
        values.append(result.stdout.strip())
    repo_root, commit, changes = values
    if Path(repo_root).resolve() != root:
        raise EvidenceError("Target must be Git repository root")
    if not HEX_GIT.fullmatch(commit):
        raise EvidenceError("Invalid target commit")
    if changes:
        raise EvidenceError("Target has uncommitted or untracked changes")
    return commit


def check_evidence(brief, report_path, stage, target=None):
    """Check artifacts, failure statuses, and exact brief/target revision binding.

    Returns a gate receipt. No external/subject-matter claims are certified.
    """
    if stage not in REQUIRED:
        raise EvidenceError("Unknown gate stage")
    if not isinstance(brief, dict) or not brief.get("goal"):
        raise EvidenceError("Brief must contain a goal")
    report_file = Path(report_path).resolve(strict=True)
    if report_file.stat().st_size > MAX_ARTIFACT_BYTES:
        raise EvidenceError("Evidence manifest too large")
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise EvidenceError("Evidence manifest is not valid JSON") from exc
    if not isinstance(report, dict) or report.get("version") != 1 or report.get("stage") != stage:
        raise EvidenceError("Evidence manifest version or stage mismatch")
    if report.get("brief_sha256") != fingerprint(brief):
        raise EvidenceError("Evidence was prepared for a different brief")
    if stage == "release":
        if target is None:
            raise EvidenceError("Release gate requires --target Git repository")
        if report.get("target_commit") != _git_commit(target):
            raise EvidenceError("Evidence is stale for current target commit")
    elif report.get("target_commit"):
        raise EvidenceError("Handoff evidence must not claim a target commit")
    entries = report.get("checks")
    if not isinstance(entries, list):
        raise EvidenceError("Evidence checks must be an array")
    mapping = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise EvidenceError("Malformed evidence check")
        name = entry["id"]
        if name in mapping:
            raise EvidenceError("Duplicate evidence check: " + name)
        mapping[name] = entry
    missing = set(REQUIRED[stage]) - mapping.keys()
    if missing:
        raise EvidenceError("Missing required evidence: " + ", ".join(sorted(missing)))
    root = report_file.parent
    for name in REQUIRED[stage]:
        item = mapping[name]
        if item.get("status") != "passed":
            raise EvidenceError("Unresolved evidence gate: " + name)
        if not isinstance(item.get("sample_count"), int) or isinstance(item["sample_count"], bool) or item["sample_count"] < MIN_SAMPLES.get(name, 1):
            raise EvidenceError("Missing executed sample count for: " + name)
        if not isinstance(item.get("method"), str) or not item["method"].strip():
            raise EvidenceError("Missing evidence collection method for: " + name)
        sha = item.get("sha256")
        if not isinstance(sha, str) or not HEX_SHA256.fullmatch(sha):
            raise EvidenceError("Missing SHA256 digest for: " + name)
        raw = _file_bytes(root, item.get("artifact"))
        if hashlib.sha256(raw).hexdigest() != sha:
            raise EvidenceError("Evidence content changed: " + name)
    return {"status": "evidence_documented", "stage": stage,
            "brief_sha256": fingerprint(brief),
            "target_commit": report.get("target_commit") if stage == "release" else None,
            "checks": list(REQUIRED[stage]),
            "warning": "Hash and recorded status only; evidence correctness and independent outcomes require human review."}


def check_codex_reviews(brief, manifest_path):
    """Require passing, unchanged external critiques for all three Codex roles.

    A review is advisory; it does not substitute for the separate evidence gate.
    """
    manifest_file = Path(manifest_path).resolve(strict=True)
    if manifest_file.stat().st_size > MAX_ARTIFACT_BYTES:
        raise EvidenceError("Codex review manifest too large")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError("Invalid Codex review manifest") from exc
    reviews = manifest.get("reviews") if isinstance(manifest, dict) and manifest.get("version") == 1 else None
    required = ("research_critic", "improvement_critic", "plan_critic")
    if not isinstance(reviews, dict) or set(reviews) != set(required):
        raise EvidenceError("Codex review manifest requires all three critic roles")
    root = manifest_file.parent
    for role in required:
        paths = reviews[role]
        if not isinstance(paths, dict):
            raise EvidenceError("Malformed Codex critic mapping")
        try:
            draft = json.loads(_file_bytes(root, paths.get("draft")))
            review = json.loads(_file_bytes(root, paths.get("review")))
        except (ValueError, UnicodeError) as exc:
            raise EvidenceError("Invalid Codex draft or review JSON") from exc
        expected_input = {"brief": brief, "draft": draft, "approved": {}, "tool_registry": []}
        if review.get("role") != role or review.get("input_hash") != fingerprint(expected_input):
            raise EvidenceError("Critic review does not match its draft: " + role)
        data = review.get("data")
        if not isinstance(data, dict) or review.get("output_hash") != fingerprint(data):
            raise EvidenceError("Critic review content changed: " + role)
        if not isinstance(review.get("identity"), str) or not review["identity"].strip():
            raise EvidenceError("Critic identity missing: " + role)
        issues = data.get("issues")
        if (data.get("verdict") != "approve" or not isinstance(issues, list) or
                any(not isinstance(item, dict) or item.get("severity") != "low" for item in issues)):
            raise EvidenceError("Unresolved critic objection: " + role)
    return {"status": "reviews_documented", "roles": list(required),
            "warning": "Model critiques are not independent factual verification."}
