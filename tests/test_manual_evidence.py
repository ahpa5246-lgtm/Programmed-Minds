"""Human review evidence complements executed checks; it never approves release."""
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from programmed_minds.checks import run_checks
from programmed_minds.pipeline import digest, run_audit, run_pipeline, load_approved
from programmed_minds.provider import ReplayProvider

FIXTURE = Path(__file__).resolve().parents[1] / "examples/replay.json"


class ManualEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture = json.loads(FIXTURE.read_text())
        req = fixture["improver"][0]["data"]["requirements"][0]
        req.update(evidence_tool="manual", test_id="review.persist")
        for gate in fixture["planner"][0]["data"]["gates"]:
            gate["required"] = gate["tool"] in {"asvs", "qodo", "superpowers"}
            gate["applicable"] = gate["required"]
        fixture["tester"][0]["data"].update(
            verdict="pass", gaps=[], issues=[],
            cases=[{"requirement_id": "R1", "scenario": "Inspect persisted notebook",
                    "steps": ["Save", "Reopen"], "expected": "Saved note persists",
                    "evidence": "manual", "status": "passed"}],
        )
        self.provider = ReplayProvider(fixture)
        self.provider.mode = "live"
        run_pipeline({"goal": "Inspect notebook persistence"}, self.provider, self.root / "run")
        _, self.approved = load_approved(self.root / "run")
        target = self.root / "target"
        (target / "tests").mkdir(parents=True)
        (target / "tests/test_smoke.py").write_text(
            "import unittest\nclass Smoke(unittest.TestCase):\n def test_load(self): self.assertEqual(2+2,4)\n"
        )
        self.report = run_checks(target, {"checks": [{"name": "python-tests"}]}, self.root / "checks")
        # A fixed revision in this audit fixture; no release/real-deployment claim.
        self.report["target_commit"] = "a" * 40
        unsigned = {k: v for k, v in self.report.items() if k != "sha256"}
        self.report["sha256"] = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.evidence_dir = self.root / "reviews"
        self.evidence_dir.mkdir()
        artifact = self.evidence_dir / "review.md"
        artifact.write_text("Fixture: reviewer recorded save and reopen checks, ASVS mapping and PR review.")
        review = {
            "status": "passed", "reviewer": "fixture-human-reviewer",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "method": "Inspect the recorded steps and mapped acceptance results",
            "artifact": "review.md", "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
        self.manual = {
            "version": 1, "approved_sha256": digest(self.approved),
            "target_commit": self.report["target_commit"],
            "requirements": [{"requirement_id": "R1", "test_id": "review.persist", **review}],
            "gates": [{"tool": tool, **review} for tool in ("asvs", "qodo", "superpowers")],
        }
        self.manual_path = self.evidence_dir / "manual.json"

    def audit(self, **options):
        self.manual_path.write_text(json.dumps(self.manual))
        return run_audit(
                self.root / "run", self.report, self.provider, self.root / "audit",
                report_dir=self.root / "checks", manual_evidence=self.manual_path, **options,
        )

    def test_recorded_manual_requirements_and_gates_can_be_verified_without_release(self):
        result = self.audit()
        self.assertEqual(result["status"], "verified", result["reasons"])
        self.assertFalse(result["release_approved"])
        self.assertEqual(result["manual_evidence"]["requirements"], ["R1"])

    def test_review_changed_during_tester_request_blocks(self):
        from unittest.mock import patch
        generate = self.provider.generate

        def changed(role, schema, context):
            reply = generate(role, schema, context)
            if role == "tester":
                (self.evidence_dir / "review.md").write_text("Changed during tester call")
            return reply

        with patch.object(self.provider, "generate", side_effect=changed):
            result = self.audit()
        self.assertEqual(result["status"], "blocked")

    def test_changed_review_artifact_blocks(self):
        (self.evidence_dir / "review.md").write_text("Changed review")
        self.assertEqual(self.audit()["status"], "blocked")

    def test_review_for_another_commit_blocks(self):
        self.manual["target_commit"] = "b" * 40
        self.assertEqual(self.audit()["status"], "blocked")

    def test_review_for_another_plan_blocks(self):
        self.manual["approved_sha256"] = "b" * 64
        self.assertEqual(self.audit()["status"], "blocked")

    def test_failed_review_cannot_be_overridden_by_model(self):
        self.manual["gates"][0]["status"] = "failed"
        self.assertEqual(self.audit()["status"], "blocked")

    def test_wrong_manual_test_identifier_blocks(self):
        self.manual["requirements"][0]["test_id"] = "unrelated.review"
        self.assertEqual(self.audit()["status"], "blocked")

    def test_missing_reviewer_blocks(self):
        self.manual["gates"][0]["reviewer"] = ""
        self.assertEqual(self.audit()["status"], "blocked")

    def test_duplicate_review_blocks(self):
        self.manual["requirements"].append(copy.deepcopy(self.manual["requirements"][0]))
        self.assertEqual(self.audit()["status"], "blocked")

    def test_path_escape_blocks(self):
        self.manual["gates"][0]["artifact"] = "../run/approved.json"
        self.assertEqual(self.audit()["status"], "blocked")

    def test_unchanged_demo_mode_still_blocks(self):
        self.provider.mode = "demo"
        self.assertEqual(self.audit()["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
