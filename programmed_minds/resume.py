"""Read immutable stage prefixes for explicit resume into a fresh run directory."""
import json
from pathlib import Path

from .evidence_gates import EvidenceError, _file_bytes, fingerprint
from .models import SCHEMAS


def load_resume(source, brief, mode, max_revisions, strict_diversity):
    root = Path(source).absolute()
    if any(item.is_symlink() for item in (root, *root.parents)) or not root.is_dir():
        raise EvidenceError("Resume source must be an existing non-symlink run directory")
    if (root / "manifest.json").exists():
        filename = "manifest.json"
    else:
        checkpoints = sorted(root.glob("progress-[0-9][0-9][0-9][0-9].json"))
        if not checkpoints:
            raise EvidenceError("Resume source has no saved stage checkpoint")
        filename = checkpoints[-1].name
    try:
        manifest = json.loads(_file_bytes(root, filename))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError("Invalid resume manifest") from exc
    if not isinstance(manifest, dict) or fingerprint(manifest.get("brief")) != fingerprint(brief):
        raise EvidenceError("Resume source belongs to a different brief")
    if manifest.get("mode") != mode:
        raise EvidenceError("Resume cannot change live/demo mode")
    if (manifest.get("max_revisions", 2) != max_revisions
            or manifest.get("strict_diversity", False) != strict_diversity):
        raise EvidenceError("Resume must retain the original review policy")
    stages = manifest.get("stages")
    if not isinstance(stages, list) or len(stages) > 100:
        raise EvidenceError("Invalid resume stage list")
    cached = []
    for index, stage in enumerate(stages, 1):
        if not isinstance(stage, dict) or stage.get("role") not in SCHEMAS:
            raise EvidenceError("Invalid saved stage")
        role = stage["role"]
        expected = f"{index:02d}-{role}.json"
        if stage.get("artifact") != expected:
            raise EvidenceError("Saved stage path is not in sequence")
        try:
            artifact = json.loads(_file_bytes(root, expected))
        except (ValueError, UnicodeError) as exc:
            raise EvidenceError("Invalid saved stage artifact") from exc
        if (not isinstance(artifact, dict) or artifact.get("role") != role
                or fingerprint(artifact.get("data")) != artifact.get("output_hash")
                or artifact.get("output_hash") != stage.get("output_hash")):
            raise EvidenceError("Saved stage content changed")
        cached.append(artifact)
    return root, cached
