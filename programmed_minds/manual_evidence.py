"""Validate owner-supplied review records, never reviewer identity or release approval."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .evidence_gates import EvidenceError, HEX_GIT, MAX_ARTIFACT_BYTES, _file_bytes, fingerprint

MANUAL_GATES = frozenset({"asvs", "superpowers", "qodo"})


def check_manual_evidence(approved, report, manifest_path):
    """Bind recorded human reviews to the exact approved plan and checked revision.

    Hashes detect stale/changed files. They do not authenticate the reviewer,
    establish independence, or prove the review's conclusions.
    """
    if manifest_path is None:
        return {"requirements": [], "gates": []}
    path = Path(manifest_path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise EvidenceError("Symlinked manual evidence paths are not allowed")
    if not path.is_file() or not 1 <= path.stat().st_size <= MAX_ARTIFACT_BYTES:
        raise EvidenceError("Manual evidence manifest missing, empty or too large")
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError("Manual evidence manifest is not valid JSON") from exc
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int or manifest["version"] != 1:
        raise EvidenceError("Manual evidence manifest version mismatch")
    if manifest.get("approved_sha256") != fingerprint(approved):
        raise EvidenceError("Manual evidence is stale for the approved plan")
    commit = report.get("target_commit")
    if not isinstance(commit, str) or not HEX_GIT.fullmatch(commit) or manifest.get("target_commit") != commit:
        raise EvidenceError("Manual evidence requires the exact checked target commit")
    requirements = {r["id"]: r for r in approved["improver"]["requirements"] if r["evidence_tool"] == "manual"}
    gates = {g["tool"] for g in approved["planner"]["gates"] if g["required"] and g["applicable"] and g["tool"] in MANUAL_GATES}

    def validate_records(key, allowed):
        records = manifest.get(key)
        if not isinstance(records, list) or len(records) > 2000:
            raise EvidenceError("Manual evidence requires bounded review arrays")
        observed = set()
        for record in records:
            identifier = record.get("requirement_id" if key == "requirements" else "tool") if isinstance(record, dict) else None
            if not isinstance(identifier, str) or identifier not in allowed or identifier in observed:
                raise EvidenceError("Unknown or duplicate manual review")
            observed.add(identifier)
            if record.get("status") != "passed":
                raise EvidenceError("Manual review is unresolved: " + identifier)
            for field in ("reviewer", "method"):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    raise EvidenceError("Manual review is missing " + field)
            try:
                reviewed = datetime.fromisoformat(record.get("reviewed_at", ""))
            except (ValueError, TypeError) as exc:
                raise EvidenceError("Manual review needs an ISO timestamp with timezone") from exc
            if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise EvidenceError("Manual review timestamp has no timezone or is in the future")
            artifact = _file_bytes(path.parent, record.get("artifact"))
            if hashlib.sha256(artifact).hexdigest() != record.get("sha256"):
                raise EvidenceError("Manual review artifact changed: " + identifier)
            if key == "requirements" and record.get("test_id") != requirements[identifier]["test_id"]:
                raise EvidenceError("Manual review test ID does not match the requirement")
        if observed != set(allowed):
            raise EvidenceError("Required manual reviews are missing")
        return sorted(observed)

    return {
        "requirements": validate_records("requirements", requirements),
        "gates": validate_records("gates", gates),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "target_commit": commit,
        "warning": "Recorded human attestation only; reviewer identity and conclusions are not authenticated. Release remains a human decision.",
    }
