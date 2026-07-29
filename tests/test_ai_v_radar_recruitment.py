from datetime import datetime, timedelta, timezone
import unittest

from scripts.fetch_ai_v_radar import Expert, is_recruitment_post, normalize_posts


NOW = datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc)
EXPERT = Expert("P0", "AI", "OpenAI", "Research", "test", "openai")


class RecruitmentFilterTests(unittest.TestCase):
    def test_apply_to_be_role_is_excluded(self) -> None:
        raw = {
            "id": "campus-lead",
            "text": "Apply to be an OpenAI Campus Lead and bring AI innovation to your campus.",
            "createdAt": (NOW - timedelta(hours=1)).isoformat(),
            "author": {"username": "openai", "name": "OpenAI"},
        }

        self.assertTrue(is_recruitment_post(raw))
        posts, dropped = normalize_posts(
            [{"source": "search", "tweets": [raw]}], [EXPERT], NOW - timedelta(hours=23), NOW, 10
        )

        self.assertEqual(posts, [])
        self.assertEqual(dropped["recruitment"], 1)


if __name__ == "__main__":
    unittest.main()
