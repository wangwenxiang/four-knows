from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import json
import sys
import unittest

from scripts.fetch_ai_v_radar import (
    Expert,
    build_hotspot_summary,
    cap_selected_posts_per_author,
    normalize_posts,
    parse_args,
    select_editorial_top_stories,
    select_diverse_top_stories,
)


NOW = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)
EXPERT = Expert("P0", "机器人", "Robot Lab", "机器人研究", "test", "robotlab")


def raw_post(post_id: str, text: str) -> dict:
    return {
        "id": post_id,
        "text": text,
        "createdAt": (NOW - timedelta(hours=1)).isoformat(),
        "author": {"username": "robotlab", "name": "Robot Lab"},
        "likeCount": 10,
        "retweetCount": 2,
        "replyCount": 1,
    }


class HotspotAttributionTest(unittest.TestCase):
    def test_hotspot_post_is_rechecked_and_tagged_after_duplicate_merge(self):
        raw = raw_post("robot-1", "Our robotics model completed a new humanoid manipulation benchmark.")
        core = {"source": "search", "tweets": [raw]}
        hotspot = {
            "source": "x-hotspot-search",
            "hotspotDirection": "robotics",
            "hotspotDirectionLabel": "机器人领域突破",
            "hotspotPostMatchAny": ["robot", "robotics", "humanoid"],
            "tweets": [raw],
            "ok": True,
            "attempts": 1,
            "elapsedSeconds": 0.1,
        }
        posts, dropped = normalize_posts([core, hotspot], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["hotspotDirections"], ["robotics"])
        self.assertEqual(posts[0]["hotspotMatches"][0]["matchedTerms"], ["robot", "robotics", "humanoid"])

        summary = build_hotspot_summary(
            [{"id": "robotics", "label": "机器人领域突破", "postMatchAny": hotspot["hotspotPostMatchAny"]}],
            [hotspot],
            posts,
            dropped,
        )
        self.assertEqual(summary["selectedPosts"], 1)
        self.assertEqual(summary["selectedPostsByDirection"], {"robotics": 1})

    def test_hotspot_post_outside_its_direction_is_dropped(self):
        hotspot = {
            "source": "x-hotspot-search",
            "hotspotDirection": "machine_consciousness",
            "hotspotDirectionLabel": "AI 意识研究",
            "hotspotPostMatchAny": ["consciousness"],
            "tweets": [raw_post("robot-2", "Our robotics model completed a humanoid manipulation benchmark.")],
        }
        posts, dropped = normalize_posts([hotspot], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(posts, [])
        self.assertEqual(dropped["hotspotDirectionMismatch:machine_consciousness"], 1)

    def test_lifestyle_team_onsite_is_not_promoted_by_one_agent_keyword(self):
        hotspot = {
            "source": "x-hotspot-search",
            "hotspotDirection": "agents",
            "hotspotDirectionLabel": "Agent 技术突破",
            "hotspotPostMatchAny": ["agent"],
            "tweets": [raw_post(
                "team-onsite",
                "The team flew into SF for a week onsite. Locked in our roadmap for AI agent document infra, then played Topgolf and soccer.",
            )],
        }
        posts, dropped = normalize_posts([hotspot], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(posts, [])
        self.assertEqual(dropped["nonTechnical"], 1)

    def test_cultural_ai_playlist_is_not_promoted_by_a_broad_ai_keyword(self):
        post = raw_post(
            "airport-ai-playlist",
            "Honolulu airport has started playing AI-generated island-themed songs on rotation.",
        )
        posts, dropped = normalize_posts([{"source": "search", "tweets": [post]}], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(posts, [])
        self.assertEqual(dropped["nonTechnical"], 1)

    def test_semantic_editorial_review_is_enabled_by_default(self):
        with patch.object(sys, "argv", ["fetch_ai_v_radar.py"]):
            self.assertTrue(parse_args().editorial_ai)



def headline_post(post_id: str, handle: str, score: int, text: str) -> dict:
    return {
        "id": post_id,
        "text": text,
        "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "AI", "role": "AI"},
        "author": {"username": handle},
        "topStoryEligible": True,
        "topStoryScore": score,
        "signalScore": score,
        "createdAtIso": NOW.isoformat(),
    }


class HeadlineEventDedupeTest(unittest.TestCase):
    def test_same_event_from_different_authors_does_not_take_two_headlines(self):
        repeated_event_a = headline_post(
            "a", "gdb", 99,
            "OpenAI cyber-capable models compromised HuggingFace production in a security incident during benchmark evaluation with zero-day vulnerabilities.",
        )
        repeated_event_b = headline_post(
            "b", "thom_wolf", 98,
            "HuggingFace describes the security incident: OpenAI cyber models compromised production during benchmark evaluation through zero-day vulnerabilities.",
        )
        independent_c = headline_post("c", "jeff", 90, "Gemini reasoning model sets a new benchmark with faster inference.")
        independent_d = headline_post("d", "arav", 89, "An agent deployment improved production search workflows.")
        selected = select_diverse_top_stories([repeated_event_a, repeated_event_b, independent_c, independent_d])
        self.assertEqual([post["id"] for post in selected], ["a", "c", "d"])

    def test_final_selection_keeps_no_more_than_three_posts_per_author(self):
        posts = [
            headline_post("a", "same", 99, "A model made a benchmark improvement."),
            headline_post("b", "same", 98, "An agent made a production improvement."),
            headline_post("c", "same", 97, "A reasoning model made an evaluation improvement."),
            headline_post("d", "same", 96, "A robotics model made a benchmark improvement."),
            headline_post("e", "other", 95, "A coding model made a benchmark improvement."),
        ]
        retained, capped = cap_selected_posts_per_author(posts)
        self.assertEqual([post["id"] for post in retained], ["a", "b", "c", "e"])
        self.assertEqual(capped, 1)

    def test_non_core_b_story_can_complete_three_qualified_headlines(self):
        def editorial_post(post_id: str, handle: str, grade: str, text: str) -> dict:
            return {
                "id": post_id,
                "text": text,
                "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "Independent Lab", "role": "Researcher", "why": "test"},
                "author": {"username": handle},
                "signalScore": 70,
                "editorial": {"dailyGrade": grade, "technicalRelevant": True},
            }

        posts = [
            editorial_post("gdb", "gdb", "A", "OpenAI released a model with benchmark inference performance improvements."),
            editorial_post("qm", "xudong", "A", "YC released an open-source multi-agent workflow system for production use."),
            editorial_post("arc", "fchollet", "B", "Base LLM benchmark results show test-time inference improves reasoning performance."),
        ]
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [
                {"id": "gdb", "category": "AI 技术进步", "rationale": "模型结果"},
                {"id": "qm", "category": "AI 技术应用", "rationale": "Agent系统"},
            ]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories(posts, retries=0)

        self.assertEqual([post["id"] for post in selected], ["gdb", "qm", "arc"])
        self.assertIn(posts[2]["topStoryCategory"], {"AI 技术进步", "AI 技术前沿", "AI 技术应用"})

    def test_concrete_evidence_displaces_a_generic_roundup_when_three_strong_candidates_exist(self):
        def editorial_post(post_id: str, handle: str, text: str) -> dict:
            return {
                "id": post_id,
                "text": text,
                "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "AI", "role": "Researcher", "why": "test"},
                "author": {"username": handle},
                "signalScore": 70,
                "editorial": {"dailyGrade": "A", "technicalRelevant": True},
            }

        posts = [
            editorial_post("roundup", "openai", "July for OpenAI Developers"),
            editorial_post("bench", "ion", "AI agent failure taxonomy boosts SWE-bench to 70.7% and TerminalBench to 89.9%."),
            editorial_post("tools", "simon", "LLM CLI adds reasoning traces, Responses API, server-side tools, and smarter logging."),
            editorial_post("safety", "anthropic", "Cybersecurity evaluation removes safeguards and studies reasoning transcripts."),
        ]
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [
                {"id": "roundup", "category": "AI 技术进步", "rationale": "月度更新"},
                {"id": "bench", "category": "AI 技术进步", "rationale": "量化评测"},
                {"id": "tools", "category": "AI 技术应用", "rationale": "工程接口"},
            ]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories(posts, retries=0)

        self.assertEqual([post["id"] for post in selected], ["bench", "tools", "safety"])


if __name__ == "__main__":
    unittest.main()
