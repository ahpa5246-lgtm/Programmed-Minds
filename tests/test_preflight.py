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
