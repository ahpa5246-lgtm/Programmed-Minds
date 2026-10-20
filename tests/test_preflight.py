"""Regression: missing mandatory evidence must not spend model calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from programmed_minds.pipeline import run_pipeline
from programmed_minds.provider import ReplayProvider

FIXTURE = Path(__file__).resolve().parents[1] / "examples/replay.json"


class PreflightTests(unittest.TestCase):
    def test_missing_live_competition_evidence_blocks_before_first_call(self):
        provider = ReplayProvider(json.loads(FIXTURE.read_text()))
        provider.mode = "live"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(provider, "generate", wraps=provider.generate) as generate:
                result = run_pipeline(
                    {"goal": "Evaluate an entry", "competition": {"name": "Example contest"}},
                    provider, Path(tmp) / "run",
                )
            self.assertEqual(result["status"], "blocked")
            self.assertIn("evidence", result.get("error", "").lower())
            generate.assert_not_called()

    def test_evidence_changed_during_designer_blocks_the_handoff(self):
        import hashlib
        from programmed_minds.evidence_gates import fingerprint, REQUIRED
        brief = {"goal": "Evaluate an entry", "competition": {"name": "Example contest"}}
        fixture = json.loads(FIXTURE.read_text())
        fixture["improver"][0]["data"]["strategy_assessment"] = {
            "decision": "go", "judging_basis": "Recorded rules",
            "differentiation": "Recorded comparison", "strongest_rival": "Existing tool",
            "failure_scenario": "Unhelpful output", "disconfirming_test": "Observed task trial",
            "evidence_ids": ["S1"], "unknowns": [],
        }
        provider = ReplayProvider(fixture)
        provider.mode = "live"
        generate = provider.generate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "observations.txt"
            artifact.write_text("Fixture collection record")
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({
                "version": 1, "stage": "handoff", "brief_sha256": fingerprint(brief),
                "checks": [{"id": name, "status": "passed", "sample_count": 2,
                            "method": "Fixture observations", "artifact": artifact.name,
                            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
                           for name in REQUIRED["handoff"]],
            }))

            def changed(role, schema, context):
                reply = generate(role, schema, context)
                if role == "designer":
                    artifact.write_text("Changed during the final model request")
                return reply

            with patch.object(provider, "generate", side_effect=changed):
                result = run_pipeline(brief, provider, root / "run", evidence_report=evidence)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse((root / "run/HANDOFF.md").exists())

    def test_invalid_live_competition_evidence_blocks_before_first_call(self):
        provider = ReplayProvider(json.loads(FIXTURE.read_text()))
        provider.mode = "live"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence.json"
            evidence.write_text('{"version": 1, "stage": "handoff", "brief_sha256": "wrong", "checks": []}')
            with patch.object(provider, "generate", wraps=provider.generate) as generate:
                result = run_pipeline(
                    {"goal": "Evaluate an entry", "competition": {"name": "Example contest"}},
                    provider, root / "run", evidence_report=evidence,
                )
            self.assertEqual(result["status"], "blocked")
            generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
