from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import fetch_ai_v_radar as radar


def expert(handle: str) -> dict[str, str]:
    return {
        "priority": "P1",
        "domain": "AI",
        "name": handle,
        "role": "Researcher",
        "why": "test",
        "handle": handle,
    }


class SearchFallbackTests(unittest.TestCase):
    def test_failed_search_batch_recovers_accounts_individually(self) -> None:
        def fake_fetch(item, count, cookie_source, retries):
            return {
                "expert": expert(item.handle),
                "experts": [expert(item.handle)],
                "label": f"@{item.handle}",
                "ok": item.handle == "recovered",
                "tweets": [{"id": "1"}] if item.handle == "recovered" else [],
                "error": "timeline unavailable" if item.handle != "recovered" else "",
                "attempts": 1,
                "elapsedSeconds": 0.01,
            }

        initial = [
            {
                "label": "search-ok",
                "ok": True,
                "experts": [expert("already_ok")],
                "tweets": [],
                "attempts": 1,
                "elapsedSeconds": 0.01,
            },
            {
                "label": "search-failed",
                "ok": False,
                "experts": [expert("recovered"), expert("still_failed")],
                "tweets": [],
                "error": "Search failed: Dependency: Unspecified",
                "attempts": 3,
                "elapsedSeconds": 1.0,
            },
        ]

        with patch.object(radar, "fetch_expert", fake_fetch):
            results, diagnostics = radar.recover_failed_search_batches(
                initial, count=20, cookie_source="chrome", retries=2, workers=1
            )

        self.assertEqual([result["label"] for result in results], ["search-ok", "@recovered", "@still_failed"])
        self.assertEqual(results[1]["source"], "timeline-fallback")
        self.assertEqual(results[1]["searchBatchError"], "Search failed: Dependency: Unspecified")
        self.assertEqual(diagnostics, [{
            "handles": ["recovered", "still_failed"],
            "error": "Search failed: Dependency: Unspecified",
            "strategy": "timeline",
        }])


class AcquisitionFailureGuardTests(unittest.TestCase):
    def test_incomplete_acquisition_preserves_audit_without_rendering_daily_artifacts(self) -> None:
        report = {
            "accountsRequested": 62,
            "accountsSucceeded": 0,
            "accountsFailed": 62,
            "xHotspotSearch": {
                "directionsRequested": 5,
                "directionsSucceeded": 0,
                "directionsFailed": 5,
            },
        }
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "20260805"
            with self.assertRaisesRegex(RuntimeError, "Acquisition incomplete"):
                radar.abort_incomplete_acquisition(output_dir, report)

            failed_audit = output_dir / "data" / "failed-run-report.json"
            self.assertTrue(failed_audit.exists())
            self.assertEqual(json.loads(failed_audit.read_text(encoding="utf-8")), report)
            self.assertFalse((output_dir / "data" / "posts.json").exists())
            self.assertFalse((output_dir / "index.html").exists())


def avatar_post(handle: str, avatar_url: str = "", quote: dict | None = None) -> dict:
    author = {"username": handle, "name": handle}
    if avatar_url:
        author["profileImageUrl"] = avatar_url
    post = {"expert": expert(handle), "author": author}
    if quote:
        post["quotedTweet"] = quote
    return post


class AvatarCacheTests(unittest.TestCase):
    def test_inline_post_avatars_are_persisted_without_profile_reads(self) -> None:
        posts = [
            avatar_post(
                "primary",
                "https://images.example/primary.jpg",
                {"author": {"username": "quoted", "profileImageUrl": "https://images.example/quoted.jpg"}},
            )
        ]
        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "avatar-cache.json"
            with patch.object(radar, "fetch_profile_avatar") as profile_fetch:
                report = radar.hydrate_post_avatars(posts, cache_path, "chrome", workers=3, retries=2)

            profile_fetch.assert_not_called()
            cache = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertEqual(report["cacheHits"], 2)
        self.assertEqual(report["inlineCached"], 2)
        self.assertEqual(report["profileRequestsNeeded"], 0)
        self.assertEqual(report["coverage"], 1.0)
        self.assertEqual(report["quotedCoverage"], 1.0)
        self.assertEqual(cache["avatars"]["primary"]["url"], "https://images.example/primary.jpg")
        self.assertEqual(cache["avatars"]["quoted"]["url"], "https://images.example/quoted.jpg")

    def test_second_run_reads_persistent_cache_without_profile_reads(self) -> None:
        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "avatar-cache.json"

            def profile_avatar(handle: str, *_args: object) -> tuple[str, str, str]:
                return handle, f"https://images.example/{handle}.jpg", ""

            first_posts = [avatar_post("primary", quote={"author": {"username": "quoted"}})]
            with patch.object(radar, "fetch_profile_avatar", side_effect=profile_avatar) as first_fetch:
                first_report = radar.hydrate_post_avatars(first_posts, cache_path, "chrome", workers=1, retries=0)

            second_posts = [avatar_post("primary", quote={"author": {"username": "quoted"}})]
            with patch.object(radar, "fetch_profile_avatar") as second_fetch:
                second_report = radar.hydrate_post_avatars(second_posts, cache_path, "chrome", workers=1, retries=0)

        self.assertEqual(first_fetch.call_count, 2)
        self.assertEqual(first_report["fetchedNow"], 2)
        second_fetch.assert_not_called()
        self.assertEqual(second_report["cacheHits"], 2)
        self.assertEqual(second_report["profileRequestsNeeded"], 0)
        self.assertEqual(second_report["coverage"], 1.0)
        self.assertEqual(second_report["quotedCoverage"], 1.0)

    def test_rate_limit_stops_unscheduled_avatar_lookups(self) -> None:
        posts = [avatar_post(handle) for handle in ("alpha", "beta", "gamma")]
        calls: list[str] = []

        def rate_limited(handle: str, *_args: object) -> tuple[str, str, str]:
            calls.append(handle)
            return handle, "", "HTTP 429 Too Many Requests"

        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "avatar-cache.json"
            with patch.object(radar, "fetch_profile_avatar", side_effect=rate_limited):
                report = radar.hydrate_post_avatars(posts, cache_path, "chrome", workers=1, retries=2)

        self.assertEqual(calls, ["alpha"])
        self.assertTrue(report["rateLimited"])
        self.assertEqual(report["attemptedNow"], 1)
        self.assertEqual(report["deferredDueToRateLimit"], 2)

    def test_profile_avatar_does_not_retry_an_http_429(self) -> None:
        completed = type("Completed", (), {"returncode": 1, "stderr": "HTTP 429 Too Many Requests", "stdout": ""})()
        with patch.object(radar.subprocess, "run", return_value=completed) as run:
            handle, url, error = radar.fetch_profile_avatar("primary", "chrome", retries=2)

        self.assertEqual((handle, url), ("primary", ""))
        self.assertTrue(radar.is_rate_limited_avatar_error(error))
        self.assertEqual(run.call_count, 1)


class EditorialBlockGuardTests(unittest.TestCase):
    """A Codex editorial-backend blocker must leave auditable evidence and never
    render or publish anything, mirroring the incomplete-acquisition guard."""

    def test_editorial_auth_failure_persists_evidence_without_rendering(self) -> None:
        now = datetime(2026, 8, 20, 7, 1, 0, tzinfo=timezone.utc)
        cutoff = now - timedelta(hours=23)
        results = [
            {"ok": True, "experts": [expert(f"alice{index}") for index in range(62)], "tweets": [], "label": "core"},
        ]
        hotspot_directions = [{"id": f"direction-{index}"} for index in range(5)]
        hotspot_results = [
            {"ok": True, "hotspotDirection": f"direction-{index}", "label": f"direction-{index}", "tweets": []}
            for index in range(5)
        ]
        candidates = [{"id": "1", "text": "AI model release", "expert": expert("alice0")}]
        error = (
            "Editorial review incomplete: unexpected status 401 Unauthorized: "
            "Incorrect API key provided: agt_code******************************JHXt"
        )

        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "20260820"
            with self.assertRaisesRegex(RuntimeError, "Editorial review blocked"):
                radar.abort_blocked_editorial(
                    output_dir,
                    now,
                    cutoff,
                    23,
                    [radar.Expert(**expert(f"alice{index}")) for index in range(62)],
                    results,
                    hotspot_directions,
                    hotspot_results,
                    candidates,
                    error,
                )

            report = json.loads((output_dir / "data" / "failed-run-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["blockedStage"], "editorial")
            self.assertEqual(report["accountsRequested"], 62)
            self.assertEqual(report["accountsSucceeded"], 62)
            self.assertEqual(report["accountsFailed"], 0)
            self.assertEqual(report["xHotspotSearch"]["directionsRequested"], 5)
            self.assertEqual(report["xHotspotSearch"]["directionsSucceeded"], 5)
            self.assertEqual(report["editorial"]["enabled"], False)
            self.assertTrue(report["editorial"]["blocked"])
            self.assertIn("401", report["editorial"]["error"])
            self.assertIn("Incorrect API key", report["editorial"]["error"])
            self.assertFalse((output_dir / "data" / "posts.json").exists())
            self.assertFalse((output_dir / "index.html").exists())
            self.assertFalse((output_dir / "screenshots.png").exists())
