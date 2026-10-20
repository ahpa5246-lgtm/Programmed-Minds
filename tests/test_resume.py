"""Resume keeps validated stages and leaves the original run untouched."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from programmed_minds.pipeline import run_pipeline
from programmed_minds.provider import ReplayProvider, ProviderError

FIXTURE = Path(__file__).resolve().parents[1] / "examples/replay.json"


class ResumeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = json.loads(FIXTURE.read_text())
        self.brief = {"goal": "Keep useful research after a provider outage"}

    def interrupted_run(self):
        source = ReplayProvider(self.fixture)
        generate = source.generate

        def interrupted(role, schema, context):
            if role == "improver":
                raise ProviderError("Provider request failed: TimeoutError")
            return generate(role, schema, context)

        with patch.object(source, "generate", side_effect=interrupted):
            result = run_pipeline(self.brief, source, self.root / "first")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["stages"]), 2)
        return self.root / "first"

    def resume(self, source, provider, brief=None):
        return run_pipeline(
                brief or self.brief, provider, self.root / "resumed", resume_from=source,
        )

    def test_resume_reuses_validated_prefix_without_repeating_model_calls(self):
        source = self.interrupted_run()
        original = {p.name: p.read_bytes() for p in source.iterdir()}
        provider = ReplayProvider(self.fixture)
        with patch.object(provider, "generate", wraps=provider.generate) as generate:
            result = self.resume(source, provider)
        self.assertEqual(result["status"], "planned", result.get("error"))
        self.assertEqual([call.args[0] for call in generate.call_args_list],
                         ["improver", "improvement_critic", "planner", "plan_critic", "designer"])
        self.assertEqual({p.name: p.read_bytes() for p in source.iterdir()}, original)
        self.assertTrue(all(s.get("reused") for s in result["stages"][:2]))

    def test_changed_brief_blocks_without_spending_calls(self):
        provider = ReplayProvider(self.fixture)
        with patch.object(provider, "generate", wraps=provider.generate) as generate:
            result = self.resume(self.interrupted_run(), provider, {"goal": "Different project"})
        self.assertEqual(result["status"], "blocked")
        generate.assert_not_called()

    def test_tampered_stage_blocks_without_spending_calls(self):
        source = self.interrupted_run()
        artifact = source / "01-researcher.json"
        data = json.loads(artifact.read_text())
        data["data"]["summary"] = "Edited after the run"
        artifact.write_text(json.dumps(data))
        provider = ReplayProvider(self.fixture)
        with patch.object(provider, "generate", wraps=provider.generate) as generate:
            result = self.resume(source, provider)
        self.assertEqual(result["status"], "blocked")
        generate.assert_not_called()

    def test_metadata_tamper_cannot_change_a_saved_critic_identity(self):
        source = self.interrupted_run()
        artifact = source / "02-research_critic.json"
        data = json.loads(artifact.read_text())
        data["identity"] = "different-endpoint|forged-critic"
        artifact.write_text(json.dumps(data))
        provider = ReplayProvider(self.fixture)
        with patch.object(provider, "generate", wraps=provider.generate) as generate:
            result = self.resume(source, provider)
        self.assertEqual(result["status"], "blocked")
        generate.assert_not_called()

    def test_mode_change_cannot_launder_demo_into_live_evidence(self):
        source = self.interrupted_run()
        provider = ReplayProvider(self.fixture)
        provider.mode = "live"
        with patch.object(provider, "generate", wraps=provider.generate) as generate:
            result = self.resume(source, provider)
        self.assertEqual(result["status"], "blocked")
        generate.assert_not_called()

    def test_checkpoint_survives_keyboard_interrupt(self):
        provider = ReplayProvider(self.fixture)
        generate = provider.generate

        def interrupted(role, schema, context):
            if role == "improver":
                raise KeyboardInterrupt()
            return generate(role, schema, context)

        with patch.object(provider, "generate", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                run_pipeline(self.brief, provider, self.root / "first")
        result = self.resume(self.root / "first", ReplayProvider(self.fixture))
        self.assertEqual(result["status"], "planned", result.get("error"))


if __name__ == "__main__":
    unittest.main()
