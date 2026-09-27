"""Replay the saved September 27 incident without X or a live model."""
import copy
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.fetch_ai_v_radar import (
    headline_selection_audit,
    same_top_story_event,
    select_editorial_top_stories,
    top_story_event_evidence,
)


class HeadlineEventRegressionTest(unittest.TestCase):
    def setUp(self):
        self.posts = json.loads((Path(__file__).parent / "fixtures/headline_event_20260927.json").read_text())
        self.by_author = {p["expert"]["handle"]: p for p in self.posts}

    def test_biology_and_quail_are_not_document_parsing(self):
        parsing = self.by_author["jerryjliu0"]
        for author in ("marinkazitnik", "sh_reya"):
            with self.subTest(author=author):
                self.assertFalse(same_top_story_event(parsing, self.by_author[author]))
                self.assertFalse(same_top_story_event(self.by_author[author], parsing))

    def test_low_fraction_word_overlap_does_not_merge_unrelated_events(self):
        left = {"text": "Orchid genomic atlas enzyme pathways tissue substrate cellular assay harvest ocean."}
        right = {"text": "Ocean satellite telemetry harvest lunar landing atlas launch thruster orbit payload."}
        self.assertFalse(same_top_story_event(left, right))

    def test_underselecting_model_is_completed_from_real_qualified_candidates(self):
        rows = [
            {"id": self.by_author[author]["id"], "category": category, "rationale": "saved editorial decision"}
            for author, category in [("Xudong07452910", "AI 技术应用"), ("jerryjliu0", "AI 技术前沿")]
        ]
        response = SimpleNamespace(returncode=0, stdout=json.dumps({"topStories": rows}), stderr="")
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=response):
            selected = select_editorial_top_stories(self.posts, retries=0)
        authors = [p["expert"]["handle"] for p in selected]
        self.assertEqual(len(set(authors)), 3)
        self.assertIn(authors[2], ["marinkazitnik", "sh_reya"])
        self.assertNotIn("bcherny", authors)
        audit = headline_selection_audit(self.posts)["candidates"]
        self.assertEqual(sum(p["reason"] == "selected" for p in audit), 3)
        self.assertEqual(next(p for p in audit if p["author"] == "bcherny")["reason"], "primary_not_substantive")

    def test_real_duplicate_remains_excluded_and_explained(self):
        original = self.by_author["marinkazitnik"]
        duplicate = copy.deepcopy(original)
        duplicate["id"] = "duplicate"
        duplicate["expert"]["handle"] = "another_author"
        evidence = top_story_event_evidence(original, duplicate)
        self.assertEqual(evidence["kind"], "shared_quote")
        response = SimpleNamespace(returncode=0, stdout=json.dumps({"topStories": [
            {"id": original["id"], "category": "AI 技术前沿"},
            {"id": duplicate["id"], "category": "AI 技术前沿"},
        ]}), stderr="")
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=response):
            selected = select_editorial_top_stories([original, duplicate], retries=0)
        self.assertEqual(len(selected), 1)
        self.assertEqual(duplicate["headlineDecision"]["reason"], "same_event")
        self.assertEqual(duplicate["headlineDecision"]["conflicts"][0]["kind"], "shared_quote")

    def test_concrete_inference_and_robotics_methods_are_not_lost_to_vocabulary(self):
        posts = json.loads((Path(__file__).parent / "fixtures/headline_methods_20260927.json").read_text())
        response = SimpleNamespace(returncode=0, stdout='{"topStories": []}', stderr="")
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=response):
            selected = select_editorial_top_stories(posts, retries=0)
        self.assertEqual({p["expert"]["handle"] for p in selected}, {"marinkazitnik", "Ken_Goldberg", "sh_reya"})


if __name__ == "__main__":
    unittest.main()
