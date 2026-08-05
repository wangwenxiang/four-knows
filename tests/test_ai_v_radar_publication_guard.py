from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import fetch_ai_v_radar as radar


class PublicationGuardTests(unittest.TestCase):
    def test_translation_status_is_factual(self) -> None:
        self.assertTrue(radar.translation_complete({"failed": 0, "coverage": 1.0}))
        self.assertFalse(radar.translation_complete({"failed": 1, "coverage": 1.0}))
        self.assertFalse(radar.translation_complete({"failed": 0, "coverage": 0.9999}))

    def test_missing_translation_gets_an_explicit_notice(self) -> None:
        post = {"text": "A source post"}
        targets = radar.collect_translation_targets([post])
        fallback_count = radar.apply_translation_fallbacks(targets, set())
        self.assertEqual(fallback_count, 1)
        self.assertEqual(post["translationZh"], radar.TRANSLATION_UNAVAILABLE)
        self.assertTrue(post["translationFallback"])

    def test_codex_translation_preflight_accepts_real_chinese_json(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": '{"preflight":"AI 智能体可以使用工具。"}',
                "stderr": "",
            },
        )()
        with patch.object(radar.subprocess, "run", return_value=completed) as run:
            result = radar.codex_translation_preflight(retries=0)

        self.assertEqual(result, {"ok": True, "attempts": 1, "error": ""})
        self.assertEqual(run.call_count, 1)

    def test_codex_translation_preflight_compacts_repeated_errors(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "returncode": 1,
                "stdout": "",
                "stderr": "readonly database\nreadonly database\nOperation not permitted",
            },
        )()
        with patch.object(radar.subprocess, "run", return_value=completed):
            result = radar.codex_translation_preflight(retries=0)

        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["error"].count("readonly database"), 1)
        self.assertIn("Operation not permitted", result["error"])

    def test_failed_preflight_publishes_with_explicit_translation_fallback(self) -> None:
        posts = [{"text": "A source post"}]
        failed_preflight = {
            "ok": False,
            "attempts": 1,
            "error": "state database is read-only",
        }
        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "translation-cache.json"
            with patch.object(radar, "translate_batch") as translate_batch:
                report = radar.translate_posts(
                    posts,
                    cache_path,
                    batch_size=8,
                    workers=2,
                    retries=0,
                    preflight=failed_preflight,
                )

        translate_batch.assert_not_called()
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["coverage"], 0.0)
        self.assertTrue(report["degraded"])
        self.assertEqual(report["fallbacks"], 1)
        self.assertEqual(posts[0]["translationZh"], radar.TRANSLATION_UNAVAILABLE)
        self.assertTrue(posts[0]["translationFallback"])


if __name__ == "__main__":
    unittest.main()
