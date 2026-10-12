"""Adversarial regression checks for contest evidence and stale-commit gates."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from programmed_minds.evidence_gates import EvidenceError, REQUIRED, check_evidence, check_codex_reviews, fingerprint


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = {"goal": "Build a trustworthy entry", "competition": {"name": "ForgeHacks"}}

    def fixture(self, stage="handoff"):
        entries = []
        for name in REQUIRED[stage]:
            file = self.root / (name + ".txt")
            file.write_text("observed evidence: " + name, encoding="utf-8")
            entries.append({"id": name, "status": "passed", "artifact": file.name,
                            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                            "sample_count": 12, "method": "small documented trial"})
        manifest = {"version": 1, "stage": stage, "brief_sha256": fingerprint(self.brief), "checks": entries}
        target = None
        if stage == "release":
            target = self.root / "target"
            target.mkdir()
            self.git(target, "init", "-q")
            self.git(target, "config", "user.email", "test@example.org")
            self.git(target, "config", "user.name", "Test")
            (target / "app.txt").write_text("original")
            self.git(target, "add", "app.txt")
            self.git(target, "commit", "-qm", "initial")
            manifest["target_commit"] = self.git(target, "rev-parse", "HEAD")
        path = self.root / "manifest.json"
        self.save(path, manifest)
        return manifest, path, target

    @staticmethod
    def git(cwd, *args):
        return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()

    @staticmethod
    def save(path, obj):
        path.write_text(json.dumps(obj), encoding="utf-8")

    def test_valid_handoff_is_not_certification(self):
        _, path, _ = self.fixture()
        receipt = check_evidence(self.brief, path, "handoff")
        self.assertEqual(receipt["status"], "evidence_documented")
        self.assertIn("human review", receipt["warning"])

    def test_missing_or_blocked_gate(self):
        report, path, _ = self.fixture()
        report["checks"].pop()
        self.save(path, report)
        with self.assertRaisesRegex(EvidenceError, "Missing required"):
            check_evidence(self.brief, path, "handoff")
        report, path, _ = self.fixture()
        report["checks"][0]["status"] = "blocked"
        self.save(path, report)
        with self.assertRaisesRegex(EvidenceError, "Unresolved"):
            check_evidence(self.brief, path, "handoff")

    def test_mutation_and_changed_brief(self):
        report, path, _ = self.fixture()
        with self.assertRaisesRegex(EvidenceError, "different brief"):
            check_evidence({"goal": "A different project"}, path, "handoff")
        (self.root / report["checks"][0]["artifact"]).write_text("altered")
        with self.assertRaisesRegex(EvidenceError, "changed"):
            check_evidence(self.brief, path, "handoff")

    def test_duplicate_or_path_traversal(self):
        report, path, _ = self.fixture()
        report["checks"].append(dict(report["checks"][0]))
        self.save(path, report)
        with self.assertRaisesRegex(EvidenceError, "Duplicate"):
            check_evidence(self.brief, path, "handoff")
        report["checks"].pop()
        report["checks"][0]["artifact"] = "../elsewhere.txt"
        self.save(path, report)
        with self.assertRaises(EvidenceError):
            check_evidence(self.brief, path, "handoff")

    def test_symlink_artifact(self):
        report, path, _ = self.fixture()
        alias = self.root / "alias.txt"
        alias.symlink_to(self.root / report["checks"][0]["artifact"])
        report["checks"][0]["artifact"] = alias.name
        self.save(path, report)
        with self.assertRaisesRegex(EvidenceError, "Symlink"):
            check_evidence(self.brief, path, "handoff")

    def test_release_is_commit_bound_and_requires_clean_tree(self):
        report, path, target = self.fixture("release")
        self.assertEqual(check_evidence(self.brief, path, "release", target)["target_commit"], report["target_commit"])
        (target / "app.txt").write_text("changed")
        with self.assertRaisesRegex(EvidenceError, "uncommitted"):
            check_evidence(self.brief, path, "release", target)
        self.git(target, "add", "app.txt")
        self.git(target, "commit", "-qm", "next")
        with self.assertRaisesRegex(EvidenceError, "stale"):
            check_evidence(self.brief, path, "release", target)

    def test_cli_release_rejects_old_audit_and_accepts_matching_revision(self):
        from programmed_minds.cli import main
        report, path, target = self.fixture("release")
        brief_path = self.root / "brief.json"
        self.save(brief_path, self.brief)
        audit_path = self.root / "audit.json"
        audit = {"status": "verified", "release_approved": False, "target_commit": "0" * 40}
        self.save(audit_path, audit)
        args = ["gate", "--stage", "release", "--brief", str(brief_path),
                "--evidence", str(path), "--target", str(target),
                "--audit-manifest", str(audit_path)]
        self.assertEqual(main(args), 2)
        audit["target_commit"] = report["target_commit"]
        self.save(audit_path, audit)
        self.assertEqual(main(args), 0)

    def test_release_requires_target(self):
        _, path, _ = self.fixture("release")
        with self.assertRaisesRegex(EvidenceError, "requires --target"):
            check_evidence(self.brief, path, "release")


class CodexReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = {"goal": "Review draft"}

    def fixture(self):
        mapping = {}
        for role in ("research_critic", "improvement_critic", "plan_critic"):
            draft = {"name": role}
            data = {"verdict": "approve", "issues": [], "summary": "passed"}
            context = {"brief": self.brief, "draft": draft, "approved": {}, "tool_registry": []}
            review = {"role": role, "data": data, "identity": "other|model",
                      "input_hash": fingerprint(context), "output_hash": fingerprint(data)}
            (self.root / (role + "-draft.json")).write_text(json.dumps(draft))
            (self.root / (role + "-review.json")).write_text(json.dumps(review))
            mapping[role] = {"draft": role + "-draft.json", "review": role + "-review.json"}
        path = self.root / "codex-manifest.json"
        path.write_text(json.dumps({"version": 1, "reviews": mapping}))
        return path, mapping

    def test_all_three_approved(self):
        path, _ = self.fixture()
        self.assertEqual(check_codex_reviews(self.brief, path)["status"], "reviews_documented")

    def test_missing_critic(self):
        path, mapping = self.fixture()
        mapping.pop("plan_critic")
        path.write_text(json.dumps({"version": 1, "reviews": mapping}))
        with self.assertRaises(EvidenceError):
            check_codex_reviews(self.brief, path)

    def test_unresolved_critic(self):
        path, _ = self.fixture()
        review_path = self.root / "research_critic-review.json"
        review = json.loads(review_path.read_text())
        review["data"]["verdict"] = "revise"
        review["output_hash"] = fingerprint(review["data"])
        review_path.write_text(json.dumps(review))
        with self.assertRaisesRegex(EvidenceError, "Unresolved"):
            check_codex_reviews(self.brief, path)

    def test_stale_draft_review(self):
        path, _ = self.fixture()
        (self.root / "research_critic-draft.json").write_text('{"name":"altered"}')
        with self.assertRaisesRegex(EvidenceError, "does not match"):
            check_codex_reviews(self.brief, path)
