#!/usr/bin/env python3
"""Validate the deterministic AI V-Radar production contract."""

from __future__ import annotations

import argparse
import hashlib
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


def parse_report_dir_date(name: str):
    if not re.fullmatch(r"\d{8}", name):
        return None
    try:
        return datetime.strptime(name, "%Y%m%d").date()
    except ValueError:
        return None


# Keep this final publication guard independent from the production selector.
# It deliberately covers role-oriented application language that previously
# passed a narrower recruitment matcher.
INDEPENDENT_RECRUITMENT_AUDIT_PATTERNS = (
    re.compile(r"\bapply to (?:be(?:come)?|join|work)\b", re.IGNORECASE),
    re.compile(r"\bapply\b.{0,80}\b(?:campus lead|fellow|intern|role|position|program)\b", re.IGNORECASE),
)


def independently_flags_recruitment(post: dict) -> bool:
    parts = [str(post.get("text") or "")]
    for nested_key in ("quotedTweet", "article"):
        nested = post.get(nested_key)
        if isinstance(nested, dict):
            parts.extend((str(nested.get("text") or ""), str(nested.get("title") or ""), str(nested.get("previewText") or "")))
    text = "\n".join(parts)
    return any(pattern.search(text) for pattern in INDEPENDENT_RECRUITMENT_AUDIT_PATTERNS)


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
    report_dirs = sorted(
        path
        for path in output_root.iterdir()
        if path.is_dir() and parse_report_dir_date(path.name) is not None
    )
    if not report_dirs:
        raise SystemExit("No dated AI V-Radar output directory found")
    output_dir = output_root / args.date if args.date else report_dirs[-1]
    posts_payload = json.loads((output_dir / "data/posts.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "data/run-report.json").read_text(encoding="utf-8"))
    html = (output_dir / "index.html").read_text(encoding="utf-8")
    posts = posts_payload.get("posts") or []
    errors: list[str] = []

    report_calendar_date = datetime.strptime(output_dir.name, "%Y%m%d").date()
    retention_cutoff = report_calendar_date - timedelta(days=7)
    expired_report_dirs = [
        path.name
        for path in report_dirs
        if parse_report_dir_date(path.name) <= retention_cutoff
    ]
    if expired_report_dirs:
        errors.append(
            "expired report directories remain after seven-day retention cleanup: "
            + ", ".join(expired_report_dirs)
        )

    fetch_started = parse_iso(report.get("fetchStartedAt") or report.get("generatedAt"))
    window_start = parse_iso(report.get("windowStart"))
    if abs((fetch_started - window_start).total_seconds() - timedelta(hours=23).total_seconds()) > 0.001:
        errors.append("window is not exactly 23 hours from fetchStartedAt")

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
        if independently_flags_recruitment(post):
            errors.append(f"post {post.get('id')} contains role-application recruitment content")
        if not is_technical_post(post):
            errors.append(f"post {post.get('id')} is not technical")
        if is_redundant_nontechnical_wrapper(post, selected_ids):
            errors.append(f"post {post.get('id')} is a redundant nontechnical quote wrapper")

    eligible_posts = [post for post in posts if post.get("topStoryEligible")]
    eligible_count = len(eligible_posts)
    required_top = 3
    if len(posts) < 3 or eligible_count < 3:
        errors.append("production poster requires three eligible AI technical top stories")
    allowed_categories = {"AI 技术进步", "AI 技术前沿", "AI 技术应用"}
    for index, post in enumerate(posts[:required_top]):
        if not post.get("isTopStory") or not post.get("topStoryEligible"):
            errors.append(f"display position {index + 1} is not an eligible top story")
        if post.get("topStoryCategory") not in allowed_categories:
            errors.append(f"display position {index + 1} has an invalid top-story category")
    if len(report.get("topStories") or []) != required_top:
        errors.append("run-report topStories does not match the required leading-card count")
    eligible_authors = {
        str((post.get("expert") or {}).get("handle") or (post.get("author") or {}).get("username") or post.get("id") or "").casefold()
        for post in eligible_posts
    }
    leading_authors = {
        str((post.get("expert") or {}).get("handle") or (post.get("author") or {}).get("username") or post.get("id") or "").casefold()
        for post in posts[:required_top]
    }
    if len(leading_authors) < min(required_top, len(eligible_authors)):
        errors.append("the first three stories do not maximize author diversity")

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

    report_date = f"{output_dir.name[:4]}-{output_dir.name[4:6]}-{output_dir.name[6:8]}"
    expected_heading = f'<h1>硅谷 AI 原声 <span class="report-date">· {report_date}</span></h1>'
    if expected_heading not in html:
        errors.append("page title and report date are not combined in one heading")
    if 'class="eyebrow"' in html or 'class="window"' in html:
        errors.append("the compact header contains a redundant date or window line")
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
        expected_input_digest = hashlib.sha256((output_dir / "data/posts.json").read_bytes()).hexdigest()
        if poster_data.get("inputSha256") != expected_input_digest:
            errors.append("poster was not generated from the current posts.json")
        if poster_data.get("monitored") != 54 or poster_data.get("selected") != 13:
            errors.append("poster stats must be 54 monitored / 13 selected")
        expected_stories = 3
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
        "expiredReportDirs": expired_report_dirs,
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
