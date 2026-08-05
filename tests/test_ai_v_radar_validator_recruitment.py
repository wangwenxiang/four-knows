import importlib.util
from pathlib import Path
import unittest


VALIDATOR_PATH = Path(__file__).parents[1] / ".agents/skills/ai-v-radar-daily/scripts/validate_radar.py"
SPEC = importlib.util.spec_from_file_location("radar_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidatorRecruitmentGuardTests(unittest.TestCase):
    def test_role_application_is_blocked_independently_of_selector(self) -> None:
        post = {"text": "Apply to be an OpenAI Campus Lead and bring AI innovation to your campus."}
        self.assertTrue(validator.independently_flags_recruitment(post))

    def test_technical_announcement_is_not_a_role_application(self) -> None:
        post = {"text": "We released an AI security benchmark and open-source evaluation tooling."}
        self.assertFalse(validator.independently_flags_recruitment(post))

    def test_cultural_ai_playlist_is_blocked_independently_of_selector(self) -> None:
        post = {
            "text": "Honolulu airport has started playing AI-generated island-themed songs on rotation.",
            "quotedTweet": {"text": "Everyone here is upset about the fake Hawaiian music."},
        }
        self.assertTrue(validator.independently_flags_low_signal_cultural_deployment(post))


if __name__ == "__main__":
    unittest.main()
