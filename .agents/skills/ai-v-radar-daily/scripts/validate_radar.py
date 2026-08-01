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

# Independent publication guard for the explicit editorial exclusion. Do not
# import the selector's constant: this must still catch a future selector bug.
FORBIDDEN_SELECTED_HANDLES = frozenset({"sama"})


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
        DEFAULT_EXPANSION_WATCHLIST,
        DEFAULT_HOTSPOT_QUERIES,
        DEFAULT_WATCHLIST,
        append_expansion_experts,
        hotspot_matches,
        is_recruitment_post,
        is_redundant_nontechnical_wrapper,
        is_low_signal_lifestyle_post,
        is_technical_post,
        load_experts,
        load_hotspot_searches,
        same_top_story_event,
        technical_context,
        term_matches,
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
    warnings: list[str] = []
    expected_experts = append_expansion_experts(
        load_experts(DEFAULT_WATCHLIST), DEFAULT_EXPANSION_WATCHLIST
    )
    expected_account_count = len(expected_experts)
    expected_hotspot_directions, _ = load_hotspot_searches(DEFAULT_HOTSPOT_QUERIES)
    expected_hotspot_by_id = {
        str(direction["id"]): direction for direction in expected_hotspot_directions
    }

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
    window_hours = float(report.get("windowHours") or posts_payload.get("windowHours") or 23)
    if window_hours <= 0 or abs((fetch_started - window_start).total_seconds() - timedelta(hours=window_hours).total_seconds()) > 0.001:
        errors.append(f"window is not exactly {window_hours:g} hours from fetchStartedAt")

    ids = [str(post.get("id") or "") for post in posts]
    if not all(ids) or len(ids) != len(set(ids)):
        errors.append("post IDs are missing or duplicated")
    selected_author_counts: dict[str, int] = {}
    for post in posts:
        author_key = str(
            (post.get("expert") or {}).get("handle")
            or (post.get("author") or {}).get("username")
            or post.get("id")
            or "unknown"
        ).casefold()
        selected_author_counts[author_key] = selected_author_counts.get(author_key, 0) + 1
    over_cap = [author for author, count in selected_author_counts.items() if count > 3]
    if over_cap:
        errors.append("a selected author exceeds the three-post cap: " + ", ".join(over_cap))
    selected_ids = set(ids)
    for post in posts:
        author_handle = str(
            (post.get("expert") or {}).get("handle")
            or (post.get("author") or {}).get("username")
            or ""
        ).lstrip("@").casefold()
        if author_handle in FORBIDDEN_SELECTED_HANDLES:
            errors.append(f"post {post.get('id')} is authored by an excluded handle: {author_handle}")
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
        if is_low_signal_lifestyle_post(post):
            errors.append(f"post {post.get('id')} is a low-signal lifestyle or company-culture post")

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
    for left_index, left in enumerate(posts[:required_top]):
        for right in posts[left_index + 1:required_top]:
            if same_top_story_event(left, right):
                errors.append("the first three stories repeat the same underlying event")

    translation = report.get("translation") or {}
    avatars = report.get("avatars") or {}
    if translation.get("failed") != 0 or translation.get("coverage") != 1.0:
        warnings.append("translation coverage is incomplete; affected cards use an explicit source-language fallback")
    if avatars.get("coverage") != 1.0 or avatars.get("quotedCoverage") != 1.0:
        errors.append("avatar coverage is incomplete")
    if avatars.get("postsWithAvatar") != report.get("postsSelected"):
        errors.append("not every selected post has a primary-author avatar")
    reported_experts = posts_payload.get("experts") or []
    reported_handles = {str(expert.get("handle") or "").casefold() for expert in reported_experts}
    expected_handles = {expert.handle.casefold() for expert in expected_experts}
    if report.get("accountsRequested") != expected_account_count or report.get("accountsFailed") != 0:
        errors.append(
            f"production fetch must request {expected_account_count} configured accounts with zero failures"
        )
    if reported_handles != expected_handles:
        errors.append("report experts do not match the configured core and expansion watchlists")
    hotspot = report.get("xHotspotSearch") or {}
    if (
        not hotspot.get("enabled")
        or hotspot.get("directionsRequested") != 5
        or hotspot.get("directionsSucceeded") != 5
        or hotspot.get("directionsFailed") != 0
    ):
        errors.append("production fetch must complete all five configured X hotspot directions")
    if int(hotspot.get("schemaVersion") or 1) >= 2:
        direction_rows = hotspot.get("directions") or []
        rows_by_id = {
            str(row.get("direction") or ""): row
            for row in direction_rows
            if isinstance(row, dict)
        }
        if set(rows_by_id) != set(expected_hotspot_by_id):
            errors.append("hotspot direction audit does not match the configured five directions")
        tagged_posts = [post for post in posts if hotspot_matches(post)]
        if hotspot.get("selectedPosts") != len(tagged_posts):
            errors.append("hotspot selected-post total does not match post provenance")
        expected_selected_by_direction = {
            direction_id: sum(
                direction_id in (post.get("hotspotDirections") or [])
                for post in tagged_posts
            )
            for direction_id in expected_hotspot_by_id
        }
        if hotspot.get("selectedPostsByDirection") != expected_selected_by_direction:
            errors.append("hotspot per-direction selected counts do not match post provenance")
        for direction_id, direction in expected_hotspot_by_id.items():
            row = rows_by_id.get(direction_id) or {}
            if row.get("postMatchAny") != direction.get("postMatchAny"):
                errors.append(f"hotspot direction {direction_id} lacks its configured post-match rule")
            if row.get("selectedPosts") != expected_selected_by_direction[direction_id]:
                errors.append(f"hotspot direction {direction_id} selected count is inconsistent")
        for post in tagged_posts:
            matches = hotspot_matches(post)
            match_ids = [str(match.get("id") or "") for match in matches]
            if list(post.get("hotspotDirections") or []) != match_ids:
                errors.append(f"post {post.get('id')} hotspot direction list is inconsistent")
            for match in matches:
                direction_id = str(match.get("id") or "")
                direction = expected_hotspot_by_id.get(direction_id)
                terms = [str(term) for term in (match.get("matchedTerms") or []) if str(term)]
                if not direction or not terms:
                    errors.append(f"post {post.get('id')} has invalid hotspot evidence")
                    continue
                if any(term not in direction.get("postMatchAny", []) for term in terms):
                    errors.append(f"post {post.get('id')} contains an unconfigured hotspot match term")
                if not any(term_matches(technical_context(post), term) for term in terms):
                    errors.append(f"post {post.get('id')} no longer satisfies its hotspot direction")

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
        if not poster_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(poster_bytes) < 33:
            errors.append("screenshots.png is not a valid PNG")
        else:
            width, height = struct.unpack(">II", poster_bytes[16:24])
            if (width, height) != (1744, 960):
                errors.append(f"poster dimensions are {width}x{height}, expected 1744x960")
            if poster_bytes[12:16] != b"IHDR" or poster_bytes[24] != 8 or poster_bytes[25] != 2:
                errors.append("screenshots.png must be an 8-bit RGB PNG")
        poster_data = json.loads(poster_data_path.read_text(encoding="utf-8"))
        expected_input_digest = hashlib.sha256((output_dir / "data/posts.json").read_bytes()).hexdigest()
        if poster_data.get("inputSha256") != expected_input_digest:
            errors.append("poster was not generated from the current posts.json")
        expected_selected = report.get("postsSelected")
        if poster_data.get("monitored") != expected_account_count or poster_data.get("selected") != expected_selected:
            errors.append(
                f"poster stats must be {expected_account_count} monitored / {expected_selected} selected"
            )
        expected_stories = 3
        if len(poster_data.get("stories") or []) != expected_stories:
            errors.append("poster story count does not match the first display records")
        if poster_data.get("copyBackend") not in {"codex", "deterministic-fallback"}:
            errors.append("poster copy backend audit is missing")
        if any(not str(story.get("title") or "").strip() for story in poster_data.get("stories") or []):
            errors.append("poster has an empty primary-story title")

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
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
