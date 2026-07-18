#!/usr/bin/env python3
"""Validate the deterministic AI V-Radar production contract."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--date", help="Report directory in YYYYMMDD; defaults to latest")
    return parser.parse_args()


def parse_iso(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    sys.path.insert(0, str(project))
    from scripts.fetch_ai_v_radar import (
        is_recruitment_post,
        is_redundant_nontechnical_wrapper,
        is_technical_post,
    )

    output_root = project / "ai-v-radar"
    report_dirs = sorted(path for path in output_root.iterdir() if path.is_dir() and re.fullmatch(r"\d{8}", path.name))
    if not report_dirs:
        raise SystemExit("No dated AI V-Radar output directory found")
    output_dir = output_root / args.date if args.date else report_dirs[-1]
    posts_payload = json.loads((output_dir / "data/posts.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "data/run-report.json").read_text(encoding="utf-8"))
    html = (output_dir / "index.html").read_text(encoding="utf-8")
    posts = posts_payload.get("posts") or []
    errors: list[str] = []

    fetch_started = parse_iso(report.get("fetchStartedAt") or report.get("generatedAt"))
    window_start = parse_iso(report.get("windowStart"))
    if abs((fetch_started - window_start).total_seconds() - timedelta(hours=17).total_seconds()) > 0.001:
        errors.append("window is not exactly 17 hours from fetchStartedAt")

    ids = [str(post.get("id") or "") for post in posts]
    if not all(ids) or len(ids) != len(set(ids)):
        errors.append("post IDs are missing or duplicated")
    selected_ids = set(ids)
    for post in posts:
        created = parse_iso(post.get("createdAtIso"))
        if not (window_start <= created <= fetch_started):
            errors.append(f"post {post.get('id')} is outside the fixed window")
        beijing = parse_iso(post.get("createdAtBeijing"))
        if beijing.utcoffset() != timedelta(hours=8):
            errors.append(f"post {post.get('id')} lacks a +08:00 Beijing timestamp")
        if not str(post.get("createdAtLocal") or "").endswith("北京"):
            errors.append(f"post {post.get('id')} lacks a visible Beijing time label")
        if is_recruitment_post(post):
            errors.append(f"post {post.get('id')} contains recruitment content")
        if not is_technical_post(post):
            errors.append(f"post {post.get('id')} is not technical")
        if is_redundant_nontechnical_wrapper(post, selected_ids):
            errors.append(f"post {post.get('id')} is a redundant nontechnical quote wrapper")

    eligible_count = sum(bool(post.get("topStoryEligible")) for post in posts)
    required_top = min(3, len(posts), eligible_count)
    allowed_categories = {"AI 技术进步", "AI 技术前沿", "AI 技术应用"}
    for index, post in enumerate(posts[:required_top]):
        if not post.get("isTopStory") or not post.get("topStoryEligible"):
            errors.append(f"display position {index + 1} is not an eligible top story")
        if post.get("topStoryCategory") not in allowed_categories:
            errors.append(f"display position {index + 1} has an invalid top-story category")
    if len(report.get("topStories") or []) != required_top:
        errors.append("run-report topStories does not match the required leading-card count")

    translation = report.get("translation") or {}
    avatars = report.get("avatars") or {}
    if translation.get("failed") != 0 or translation.get("coverage") != 1.0:
        errors.append("translation coverage is incomplete")
    if avatars.get("coverage") != 1.0 or avatars.get("quotedCoverage") != 1.0:
        errors.append("avatar coverage is incomplete")
    if avatars.get("postsWithAvatar") != report.get("postsSelected"):
        errors.append("not every selected post has a primary-author avatar")
    if report.get("accountsRequested") != 54 or report.get("accountsFailed") != 0:
        errors.append("production fetch must request 54 accounts with zero failures")

    if "<h1>硅谷 AI 原声日报</h1>" not in html:
        errors.append("page title contract is missing")
    if html.count('class="signal-card"') != len(posts):
        errors.append("HTML card count does not match posts.json")
    first_card_tags = re.findall(r'<article class="signal-card"[^>]*>', html)[:required_top]
    if len(first_card_tags) != required_top or any('data-top-story="true"' not in tag for tag in first_card_tags):
        errors.append("the first HTML cards are not marked as top stories")
    banned_ui = ('class="filters"', 'class="expert-nav"', 'id="search"', 'class="language-switch"')
    if any(marker in html for marker in banned_ui):
        errors.append("density-reducing controls were reintroduced")

    poster_path = output_dir / "screenshots.png"
    poster_data_path = output_dir / "data/poster.json"
    if not poster_path.exists() or not poster_data_path.exists():
        errors.append("daily poster outputs are missing")
    else:
        poster_bytes = poster_path.read_bytes()
        if not poster_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(poster_bytes) < 24:
            errors.append("screenshots.png is not a valid PNG")
        else:
            width, height = struct.unpack(">II", poster_bytes[16:24])
            if (width, height) != (1744, 960):
                errors.append(f"poster dimensions are {width}x{height}, expected 1744x960")
        poster_data = json.loads(poster_data_path.read_text(encoding="utf-8"))
        if poster_data.get("monitored") != 54 or poster_data.get("selected") != 13:
            errors.append("poster stats must be 54 monitored / 13 selected")
        expected_stories = min(3, len(posts))
        if len(poster_data.get("stories") or []) != expected_stories:
            errors.append("poster story count does not match the first display records")

    summary = {
        "ok": not errors,
        "output": str(output_dir / "index.html"),
        "windowStart": window_start.isoformat(),
        "fetchStartedAt": fetch_started.isoformat(),
        "posts": len(posts),
        "topStories": report.get("topStories") or [],
        "poster": str(poster_path),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
