#!/usr/bin/env python3
"""Fetch a read-only 23-hour X radar with Bird and render a static report."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import html
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCHLIST = ROOT / "ai_key_people_watchlist_visual.html"
DEFAULT_OUTPUT_ROOT = ROOT / "ai-v-radar"
SHANGHAI = ZoneInfo("Asia/Shanghai")
TWITTER_DATE = "%a %b %d %H:%M:%S %z %Y"


@dataclasses.dataclass(frozen=True)
class Expert:
    priority: str
    domain: str
    name: str
    role: str
    why: str
    handle: str


THEMES = {
    "coding": ("AI 编程与 Agent", "Coding & Agents"),
    "models": ("模型、研究与评测", "Models & Research"),
    "products": ("产品与商业化", "Products & Business"),
    "infra": ("基础设施与效率", "Infrastructure"),
    "governance": ("安全、政策与治理", "Safety & Governance"),
}


THEME_KEYWORDS = {
    "coding": (
        "agent", "coding", "code", "developer", "software", "cursor", "claude code",
        "mcp", "langchain", "llamaindex", "rag", "eval", "workflow", "devin",
    ),
    "models": (
        "model", "benchmark", "reasoning", "training", "research", "paper", "llm",
        "gpt", "claude", "gemini", "mistral", "transformer", "alignment", "rlhf",
    ),
    "products": (
        "launch", "release", "product", "users", "customer", "revenue", "startup",
        "company", "app", "pricing", "subscription", "available", "shipping",
    ),
    "infra": (
        "gpu", "tpu", "inference", "token", "latency", "throughput", "compute",
        "datacenter", "data center", "kernel", "attention", "quantization", "cost",
    ),
    "governance": (
        "safety", "security", "policy", "regulation", "government", "risk", "attack",
        "interpretability", "governance", "law", "responsible", "society",
    ),
}


DOMAIN_THEME_HINTS = {
    "编程": "coding",
    "Agent": "coding",
    "RAG": "coding",
    "工程": "coding",
    "基础设施": "infra",
    "硬件": "infra",
    "训练优化": "infra",
    "安全": "governance",
    "政策": "governance",
    "治理": "governance",
    "产品": "products",
    "搜索": "products",
    "视频": "products",
    "研究": "models",
    "模型": "models",
    "评测": "models",
}


TECHNICAL_KEYWORDS = (
    "ai", "artificial intelligence", "llm", "vlm", "ml", "machine learning",
    "gpt", "claude", "gemini", "openai", "anthropic", "perplexity", "mistral",
    "model", "agent", "agentic", "rag", "prompt", "token", "reasoning", "eval",
    "benchmark", "training", "inference", "fine-tun", "distill", "alignment",
    "interpretability", "neural", "transformer", "open-source", "open source",
    "open-weight", "open weight", "research", "paper", "dataset", "algorithm",
    "coding", "code", "software", "developer", "api", "sdk", "github", "repo",
    "database", "server", "linux", "x86", "gpu", "compute", "hardware", "robot",
    "robotics", "cyber", "security", "vulnerabil", "deployment", "workflow",
    "automation", "tool", "memory", "planning", "trace", "ocr", "parser",
    "latency", "throughput", "quantization", "kernel", "data center", "datacenter",
    "digital infrastructure", "technical", "technology", "prod data",
    "graph engineering", "loop engineering", "huggingface", "kaggle", "langchain",
    "llamaindex", "crewai", "cursor", "devin",
)


TECHNICAL_URL_MARKERS = ("github.com/", "arxiv.org/", "huggingface.co/", "kaggle.com/")


RECRUITMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:we(?:['’]re| are)|i(?:['’]m| am)) hiring\b",
        r"\b(?:need|looking|want) to hire\b",
        r"\bhiring (?:for|a|an)\b",
        r"\bhiring\b.{0,80}\b(?:engineer|researcher|designer|team|role|position)\b",
        r"\bjoin (?:our|the) team\b",
        r"\bcome work (?:with|for) us\b",
        r"\bopen (?:role|roles|position|positions)\b",
        r"\bapplications? (?:are )?open\b",
        r"\bjob (?:opening|openings|opportunity|opportunities)\b",
        r"\bapply (?:here|now|for)\b",
        # Recruitment calls often use role-oriented wording rather than
        # "apply for": e.g. "Apply to be an OpenAI Campus Lead".
        r"\bapply to (?:be(?:come)?|join|work)\b",
        r"\b(?:good|great) role for you\b",
        r"\bthis role (?:is|could be) for you\b",
        r"\brecruit(?:ing|er|ers|ment)\b",
        r"\bcareers? page\b",
        r"(?:招聘|招人|加入我们|职位开放|岗位开放)",
    )
)


NONTECHNICAL_PRIMARY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bswag\b",
        r"\bmerch(?:andise)?\b",
        r"\b(?:team|company) (?:offsite|retreat)\b",
        r"\b(?:team|company) dinner\b",
    )
)


TOP_STORY_CORE_TERMS = (
    "ai", "llm", "vlm", "gpt", "claude", "model", "agent", "reasoning",
    "training", "inference", "benchmark", "eval", "coding", "software",
    "api", "github", "open-source", "open source", "open-weight", "open weight",
    "robot", "cyber", "vulnerab", "security", "ocr", "workflow", "quantiz",
    "lora", "dataset", "algorithm", "transformer", "interpretability",
)


TOP_STORY_PROGRESS_TERMS = (
    "state of the art", "sota", "new", "launch", "release", "ship", "shipped", "shipping", "first",
    "improv", "faster", "better", "accuracy", "performance", "efficien",
    "benchmark", "result", "breakthrough", "support", "available", "%",
)


TOP_STORY_FRONTIER_TERMS = (
    "frontier", "state of the art", "sota", "novel", "research", "paper",
    "benchmark", "training", "reasoning", "interpretability", "alignment",
    "distill", "open-weight", "open weight", "architecture", "scaling",
)


TOP_STORY_APPLICATION_TERMS = (
    "use", "apply", "deploy", "production", "workflow", "coding", "review",
    "security", "secure", "system", "robot", "agent", "api", "ocr", "tool",
    "developer", "automation", "infrastructure", "data center", "datacenter",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--hours", type=float, default=23.0)
    parser.add_argument("--count-per-user", type=int, default=20)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--fetch-mode", choices=("search", "timeline"), default="search")
    parser.add_argument("--search-batch-size", type=int, default=8)
    parser.add_argument("--search-max-pages", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="Only fetch the first N experts")
    parser.add_argument("--max-posts", type=int, default=120)
    parser.add_argument("--cookie-source", default="chrome")
    parser.add_argument("--no-translate", dest="translate", action="store_false", help="Skip Codex translation")
    parser.set_defaults(translate=True)
    parser.add_argument("--translation-batch-size", type=int, default=18)
    parser.add_argument("--translation-workers", type=int, default=2)
    parser.add_argument("--translation-retries", type=int, default=1)
    parser.add_argument("--translation-cache", type=Path, help="Persistent translation cache JSON")
    parser.add_argument("--no-avatars", dest="avatars", action="store_false", help="Skip X avatar enrichment")
    parser.set_defaults(avatars=True)
    parser.add_argument("--avatar-workers", type=int, default=3)
    parser.add_argument("--avatar-cache", type=Path, help="Persistent X avatar cache JSON")
    parser.add_argument("--reuse-data", type=Path, help="Skip Bird and rebuild from an existing posts.json")
    parser.add_argument("--now", help="ISO timestamp override for deterministic reruns")
    return parser.parse_args()


def extract_js_string(line: str, key: str) -> str:
    match = re.search(rf'{re.escape(key)}:"((?:\\.|[^"\\])*)"', line)
    if not match:
        return ""
    return match.group(1).replace(r"\"", '"').replace(r"\n", "\n").replace(r"\\", "\\")


def load_experts(path: Path) -> list[Expert]:
    experts: list[Expert] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        x_url = extract_js_string(line, "x")
        match = re.fullmatch(r"https://x\.com/([^/?#]+)", x_url)
        if not match:
            continue
        handle = match.group(1)
        key = handle.casefold()
        if key in seen:
            continue
        seen.add(key)
        experts.append(
            Expert(
                priority=extract_js_string(line, "priority") or "P1",
                domain=extract_js_string(line, "domain") or "AI",
                name=extract_js_string(line, "name") or handle,
                role=extract_js_string(line, "role"),
                why=extract_js_string(line, "why"),
                handle=handle,
            )
        )
    if not experts:
        raise RuntimeError(f"No X accounts found in {path}")
    return experts


def redact(message: str) -> str:
    message = re.sub(r"(?i)(auth_token|ct0)([=:]\s*)\S+", r"\1\2[redacted]", message)
    message = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~-]+", r"\1[redacted]", message)
    return message[-1200:]


def normalize_bird_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        tweets = payload.get("tweets", [])
        if isinstance(tweets, list):
            return [item for item in tweets if isinstance(item, dict)]
    return []


def extract_avatar_map(payload: Any) -> dict[str, str]:
    avatars: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            avatar = value.get("avatar")
            core = value.get("core")
            legacy = value.get("legacy")
            image_url = avatar.get("image_url") if isinstance(avatar, dict) else ""
            username = ""
            if isinstance(core, dict):
                username = str(core.get("screen_name") or "")
            if not username and isinstance(legacy, dict):
                username = str(legacy.get("screen_name") or "")
                image_url = image_url or str(legacy.get("profile_image_url_https") or legacy.get("profile_image_url") or "")
            if username and image_url:
                avatars[username.casefold()] = str(image_url)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return avatars


def attach_author_avatars(tweets: list[dict[str, Any]], avatars: dict[str, str]) -> None:
    def attach(tweet: Any) -> None:
        if not isinstance(tweet, dict):
            return
        author = tweet.get("author")
        if isinstance(author, dict):
            username = str(author.get("username") or "").casefold()
            if avatars.get(username):
                author["profileImageUrl"] = avatars[username]
        attach(tweet.get("quotedTweet"))

    for tweet in tweets:
        attach(tweet)


def load_avatar_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "avatars": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "avatars": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("avatars"), dict):
        return {"version": 1, "avatars": {}}
    return payload


def avatar_from_truncated_json(output: str, handle: str) -> str:
    escaped_handle = re.escape(handle)
    patterns = (
        rf'"avatar"\s*:\s*\{{\s*"image_url"\s*:\s*"([^"]+)"\s*\}}.{{0,4000}}?"screen_name"\s*:\s*"{escaped_handle}"',
        rf'"screen_name"\s*:\s*"{escaped_handle}".{{0,4000}}?"avatar"\s*:\s*\{{\s*"image_url"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, output, re.S | re.I)
        if match:
            try:
                return str(json.loads(f'"{match.group(1)}"'))
            except json.JSONDecodeError:
                return match.group(1).replace(r"\/", "/")
    return ""


def fetch_profile_avatar(handle: str, cookie_source: str, retries: int) -> tuple[str, str, str]:
    command = [
        "bird", "--cookie-source", cookie_source, "user-tweets", handle,
        "-n", "1", "--json-full",
    ]
    last_error = ""
    for attempt in range(max(0, retries) + 1):
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
        else:
            if completed.returncode == 0:
                avatar = ""
                try:
                    payload = json.loads(completed.stdout)
                except json.JSONDecodeError:
                    avatar = avatar_from_truncated_json(completed.stdout, handle)
                else:
                    avatar = extract_avatar_map(payload).get(handle.casefold(), "")
                if avatar:
                    return handle, avatar, ""
                last_error = "Avatar not found in Bird profile response"
            else:
                last_error = redact(completed.stderr or completed.stdout or f"exit {completed.returncode}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    return handle, "", last_error


def hydrate_post_avatars(
    posts: list[dict[str, Any]],
    cache_path: Path,
    cookie_source: str,
    workers: int,
    retries: int,
) -> dict[str, Any]:
    cache = load_avatar_cache(cache_path)
    cached_avatars = cache["avatars"]
    primary_handles = {str((post.get("author") or {}).get("username") or post["expert"]["handle"]) for post in posts}
    quote_handles = {
        str(((post.get("quotedTweet") or {}).get("author") or {}).get("username"))
        for post in posts
        if isinstance(post.get("quotedTweet"), dict) and ((post.get("quotedTweet") or {}).get("author") or {}).get("username")
    }
    all_handles = sorted(primary_handles | quote_handles, key=str.casefold)
    missing = [handle for handle in all_handles if not isinstance(cached_avatars.get(handle.casefold()), dict) or not cached_avatars[handle.casefold()].get("url")]
    errors: list[dict[str, str]] = []
    fetched = 0
    if missing:
        print(f"Fetching {len(missing)} real X author avatars with Bird...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch_profile_avatar, handle, cookie_source, retries): handle for handle in missing}
            for future in concurrent.futures.as_completed(futures):
                handle, url, error = future.result()
                if url:
                    cached_avatars[handle.casefold()] = {"username": handle, "url": url, "updatedAt": datetime.now(timezone.utc).isoformat()}
                    fetched += 1
                else:
                    errors.append({"handle": handle, "error": error})

    avatar_map = {
        key: str(entry.get("url"))
        for key, entry in cached_avatars.items()
        if isinstance(entry, dict) and entry.get("url")
    }
    attach_author_avatars(posts, avatar_map)
    cache["version"] = 1
    cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    with_avatar = sum(bool((post.get("author") or {}).get("profileImageUrl")) for post in posts)
    quoted_posts = [post["quotedTweet"] for post in posts if isinstance(post.get("quotedTweet"), dict)]
    quoted_with_avatar = sum(bool((quote.get("author") or {}).get("profileImageUrl")) for quote in quoted_posts)
    return {
        "enabled": True,
        "authors": len(all_handles),
        "primaryAuthors": len(primary_handles),
        "quotedAuthors": len(quote_handles),
        "cacheHits": len(all_handles) - len(missing),
        "fetchedNow": fetched,
        "postsWithAvatar": with_avatar,
        "coverage": round(with_avatar / len(posts), 4) if posts else 1.0,
        "quotedPostsWithAvatar": quoted_with_avatar,
        "quotedCoverage": round(quoted_with_avatar / len(quoted_posts), 4) if quoted_posts else 1.0,
        "errors": errors[:10],
        "cache": str(cache_path),
    }


def fetch_expert(
    expert: Expert,
    count: int,
    cookie_source: str,
    retries: int,
) -> dict[str, Any]:
    command = [
        "bird",
        "--cookie-source",
        cookie_source,
        "user-tweets",
        expert.handle,
        "-n",
        str(count),
        "--json",
    ]
    started = time.monotonic()
    last_error = ""
    for attempt in range(retries + 1):
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = "Bird timed out after 90 seconds"
        else:
            if completed.returncode == 0:
                try:
                    payload = json.loads(completed.stdout)
                    tweets = normalize_bird_payload(payload)
                    attach_author_avatars(tweets, extract_avatar_map(payload))
                except json.JSONDecodeError as exc:
                    last_error = f"Invalid Bird JSON: {exc}"
                else:
                    return {
                        "expert": dataclasses.asdict(expert),
                        "experts": [dataclasses.asdict(expert)],
                        "label": f"@{expert.handle}",
                        "ok": True,
                        "tweets": tweets,
                        "elapsedSeconds": round(time.monotonic() - started, 2),
                        "attempts": attempt + 1,
                    }
            else:
                last_error = redact(completed.stderr or completed.stdout or f"exit {completed.returncode}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    return {
        "expert": dataclasses.asdict(expert),
        "experts": [dataclasses.asdict(expert)],
        "label": f"@{expert.handle}",
        "ok": False,
        "tweets": [],
        "error": last_error,
        "elapsedSeconds": round(time.monotonic() - started, 2),
        "attempts": retries + 1,
    }


def fetch_search_batch(
    experts: list[Expert],
    cutoff: datetime,
    cookie_source: str,
    max_pages: int,
    retries: int,
) -> dict[str, Any]:
    handles = [expert.handle for expert in experts]
    query = "(" + " OR ".join(f"from:{handle}" for handle in handles) + ")"
    query += f" since:{cutoff.astimezone(timezone.utc):%Y-%m-%d} -filter:retweets"
    command = [
        "bird",
        "--cookie-source",
        cookie_source,
        "search",
        query,
        "--all",
        "--max-pages",
        str(max(1, max_pages)),
        "--json",
    ]
    started = time.monotonic()
    last_error = ""
    for attempt in range(retries + 1):
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = "Bird batch search timed out after 120 seconds"
        else:
            if completed.returncode == 0:
                try:
                    payload = json.loads(completed.stdout)
                    tweets = normalize_bird_payload(payload)
                    attach_author_avatars(tweets, extract_avatar_map(payload))
                except json.JSONDecodeError as exc:
                    last_error = f"Invalid Bird JSON: {exc}"
                else:
                    return {
                        "experts": [dataclasses.asdict(expert) for expert in experts],
                        "label": ", ".join(f"@{handle}" for handle in handles),
                        "ok": True,
                        "tweets": tweets,
                        "elapsedSeconds": round(time.monotonic() - started, 2),
                        "attempts": attempt + 1,
                        "source": "search",
                    }
            else:
                last_error = redact(completed.stderr or completed.stdout or f"exit {completed.returncode}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    return {
        "experts": [dataclasses.asdict(expert) for expert in experts],
        "label": ", ".join(f"@{handle}" for handle in handles),
        "ok": False,
        "tweets": [],
        "error": last_error,
        "elapsedSeconds": round(time.monotonic() - started, 2),
        "attempts": retries + 1,
        "source": "search",
    }


def parse_created_at(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for parser in (
        lambda raw: datetime.strptime(raw, TWITTER_DATE),
        lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")),
    ):
        try:
            parsed = parser(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def technical_context(post: dict[str, Any]) -> str:
    parts = [str(post.get("text") or "")]
    article = post.get("article")
    if isinstance(article, dict):
        parts.extend((str(article.get("title") or ""), str(article.get("previewText") or "")))
    quote = post.get("quotedTweet")
    if isinstance(quote, dict):
        parts.append(str(quote.get("text") or ""))
        quote_article = quote.get("article")
        if isinstance(quote_article, dict):
            parts.extend((str(quote_article.get("title") or ""), str(quote_article.get("previewText") or "")))
    return "\n".join(parts).casefold()


def is_technical_post(post: dict[str, Any]) -> bool:
    text = technical_context(post)
    if any(marker in text for marker in TECHNICAL_URL_MARKERS):
        return True
    for keyword in TECHNICAL_KEYWORDS:
        normalized = keyword.casefold()
        if normalized.isalnum() and len(normalized) <= 4:
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
                return True
        elif normalized in text:
            return True
    return False


def is_recruitment_post(post: dict[str, Any]) -> bool:
    text = technical_context(post)
    return any(pattern.search(text) for pattern in RECRUITMENT_PATTERNS)


def is_redundant_nontechnical_wrapper(post: dict[str, Any], selected_ids: set[str]) -> bool:
    """Drop lifestyle wrappers when their substantive quote is already selected directly."""
    primary_text = str(post.get("text") or "")
    if not any(pattern.search(primary_text) for pattern in NONTECHNICAL_PRIMARY_PATTERNS):
        return False
    quote = post.get("quotedTweet")
    quote_id = str(quote.get("id") or "") if isinstance(quote, dict) else ""
    return bool(quote_id and quote_id in selected_ids)


def strategic_org_rank(expert: Expert) -> int:
    affiliation = f"{expert.domain} {expert.role}".casefold()
    affiliation = re.sub(r"(?:前|former|ex[- ]?)\s*openai", "", affiliation)
    if "openai" in affiliation:
        return 0
    if "anthropic" in affiliation or "claude" in affiliation:
        return 1
    return 2


def count_term_hits(text: str, terms: tuple[str, ...]) -> int:
    hits = 0
    for term in terms:
        normalized = term.casefold()
        if normalized.isalnum() and len(normalized) <= 4:
            hits += int(bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text)))
        else:
            hits += int(normalized in text)
    return hits


def top_story_profile(post: dict[str, Any], expert: Expert) -> tuple[bool, int, str]:
    text = technical_context(post)
    core_hits = count_term_hits(text, TOP_STORY_CORE_TERMS)
    progress_hits = count_term_hits(text, TOP_STORY_PROGRESS_TERMS)
    frontier_hits = count_term_hits(text, TOP_STORY_FRONTIER_TERMS)
    application_hits = count_term_hits(text, TOP_STORY_APPLICATION_TERMS)
    dimension_hits = progress_hits + frontier_hits + application_hits
    eligible = core_hits >= 1 and dimension_hits >= 2 and not is_recruitment_post(post)
    category_counts = {
        "AI 技术进步": progress_hits,
        "AI 技术前沿": frontier_hits,
        "AI 技术应用": application_hits,
    }
    category = max(category_counts, key=category_counts.get)
    likes = max(0, int(post.get("likeCount") or 0))
    reposts = max(0, int(post.get("retweetCount") or 0))
    replies = max(0, int(post.get("replyCount") or 0))
    engagement = likes + reposts * 2 + replies * 1.5
    org_rank = strategic_org_rank(expert)
    score = 40 if org_rank == 0 else 36 if org_rank == 1 else 14 if expert.priority == "P0" else 5
    score += min(28, core_hits * 3 + progress_hits * 2 + frontier_hits * 3 + application_hits * 2)
    score += min(20, round(math.log10(engagement + 1) * 7))
    score += 4 if post.get("quotedTweet") else 0
    score += 3 if post.get("article") else 0
    return eligible, min(99, score), category


def attach_editorial_rank(post: dict[str, Any], expert: Expert) -> None:
    eligible, score, category = top_story_profile(post, expert)
    post["topStoryEligible"] = eligible
    post["topStoryScore"] = score
    post["topStoryCategory"] = category


def classify_theme(post: dict[str, Any], expert: Expert) -> str:
    text = " ".join(
        str(value or "")
        for value in (
            post.get("text"),
            (post.get("quotedTweet") or {}).get("text") if isinstance(post.get("quotedTweet"), dict) else "",
            (post.get("article") or {}).get("title") if isinstance(post.get("article"), dict) else "",
        )
    ).casefold()
    scores = Counter()
    for theme, words in THEME_KEYWORDS.items():
        scores[theme] += sum(1 for word in words if word.casefold() in text)
    for hint, theme in DOMAIN_THEME_HINTS.items():
        if hint.casefold() in expert.domain.casefold():
            scores[theme] += 2
    return scores.most_common(1)[0][0] if scores else "models"


def signal_score(post: dict[str, Any], expert: Expert) -> int:
    likes = max(0, int(post.get("likeCount") or 0))
    reposts = max(0, int(post.get("retweetCount") or 0))
    replies = max(0, int(post.get("replyCount") or 0))
    engagement = likes + reposts * 2 + replies * 1.5
    score = 52 if expert.priority == "P0" else 42
    org_rank = strategic_org_rank(expert)
    score += 10 if org_rank == 0 else 9 if org_rank == 1 else 0
    score += min(32, round(math.log10(engagement + 1) * 11))
    score += 4 if post.get("quotedTweet") else 0
    score += 4 if post.get("article") else 0
    score += 3 if post.get("media") else 0
    score += 3 if len(str(post.get("text") or "")) >= 240 else 0
    return min(99, score)


def normalize_posts(
    results: list[dict[str, Any]],
    experts: list[Expert],
    cutoff: datetime,
    now: datetime,
    max_posts: int,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    posts_by_id: dict[str, dict[str, Any]] = {}
    dropped = Counter()
    experts_by_handle = {expert.handle.casefold(): expert for expert in experts}
    for result in results:
        for raw in result.get("tweets", []):
            username = str((raw.get("author") or {}).get("username") or "")
            expert = experts_by_handle.get(username.casefold())
            if expert is None:
                dropped["unmatchedAuthor"] += 1
                continue
            created_at = parse_created_at(str(raw.get("createdAt") or ""))
            if not created_at:
                dropped["invalidDate"] += 1
                continue
            created_at = created_at.astimezone(timezone.utc)
            if created_at < cutoff.astimezone(timezone.utc) or created_at > now.astimezone(timezone.utc):
                dropped["outsideWindow"] += 1
                continue
            post_id = str(raw.get("id") or "").strip()
            if not post_id:
                dropped["missingId"] += 1
                continue
            conversation_id = str(raw.get("conversationId") or "")
            is_reply = bool(conversation_id and conversation_id != post_id)
            engagement = int(raw.get("likeCount") or 0) + int(raw.get("retweetCount") or 0)
            if is_reply and not (raw.get("quotedTweet") or raw.get("media") or engagement >= 50):
                dropped["lowSignalReply"] += 1
                continue
            if is_recruitment_post(raw):
                dropped["recruitment"] += 1
                continue
            if not is_technical_post(raw):
                dropped["nonTechnical"] += 1
                continue
            post = dict(raw)
            post["id"] = post_id
            post["expert"] = dataclasses.asdict(expert)
            post["createdAtIso"] = created_at.isoformat()
            post["createdAtBeijing"] = created_at.astimezone(SHANGHAI).isoformat()
            post["createdAtLocal"] = created_at.astimezone(SHANGHAI).strftime("%m-%d %H:%M 北京")
            username = username or expert.handle
            post["url"] = f"https://x.com/{username}/status/{post_id}"
            post["themeId"] = classify_theme(post, expert)
            post["signalScore"] = signal_score(post, expert)
            attach_editorial_rank(post, expert)
            existing = posts_by_id.get(post_id)
            if existing is None or post["signalScore"] > existing["signalScore"]:
                posts_by_id[post_id] = post
    selected_ids = set(posts_by_id)
    redundant_wrapper_ids = {
        post_id
        for post_id, post in posts_by_id.items()
        if is_redundant_nontechnical_wrapper(post, selected_ids)
    }
    for post_id in redundant_wrapper_ids:
        posts_by_id.pop(post_id, None)
        dropped["nonTechnical"] += 1
    posts = sorted(
        posts_by_id.values(),
        key=lambda item: (item["signalScore"], item["createdAtIso"]),
        reverse=True,
    )
    if len(posts) > max_posts:
        dropped["maxPosts"] += len(posts) - max_posts
        posts = posts[:max_posts]
    return posts, dropped


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CJK = re.compile(r"[\u3400-\u9fff]")
TRANSLATION_PROMPT_VERSION = "codex-v1"
CODEX_EXEC_COMMAND = [
    "codex",
    "-a",
    "never",
    "--sandbox",
    "read-only",
    "-C",
    "/private/tmp",
    "exec",
    "--ephemeral",
    "--ignore-user-config",
    "--skip-git-repo-check",
    "-",
]


def needs_translation(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    cjk_count = len(CJK.findall(text))
    visible_count = len(re.sub(r"\s+", "", text))
    if cjk_count >= 6 and cjk_count / max(1, visible_count) >= 0.15:
        return False
    return bool(re.search(r"[A-Za-z\u3040-\u30ff\uac00-\ud7af]", text))


def translation_key(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def collect_translation_targets(posts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}

    def add(container: Any, source_field: str, target_field: str) -> None:
        if not isinstance(container, dict):
            return
        text = str(container.get(source_field) or "").strip()
        if not needs_translation(text):
            return
        key = translation_key(text)
        target = targets.setdefault(key, {"text": text, "destinations": []})
        target["destinations"].append((container, target_field))

    for post in posts:
        add(post, "text", "translationZh")
        article = post.get("article")
        add(article, "title", "titleZh")
        add(article, "previewText", "previewTextZh")
        quote = post.get("quotedTweet")
        add(quote, "text", "translationZh")
        if isinstance(quote, dict):
            quote_article = quote.get("article")
            add(quote_article, "title", "titleZh")
            add(quote_article, "previewText", "previewTextZh")
    return targets


def load_translation_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "translations": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "translations": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("translations"), dict):
        return {"version": 1, "translations": {}}
    return payload


def parse_translation_json(output: str) -> dict[str, str]:
    cleaned = ANSI_ESCAPE.sub("", output).strip()
    candidates = [match.group(1) for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.S | re.I)]
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(json.dumps(value, ensure_ascii=False))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return {str(key): str(text).strip() for key, text in value.items() if str(text).strip()}
    raise ValueError("Codex did not return a JSON object")


def translate_batch(batch: dict[str, str], retries: int) -> tuple[dict[str, str], str]:
    collected: dict[str, str] = {}
    remaining = dict(batch)
    last_error = ""
    for attempt in range(max(0, retries) + 1):
        prompt = (
            "你是 AI 行业日报的专业中英翻译。请把下方 JSON 对象中每个 value 翻译成自然、准确、简洁的简体中文。\n"
            "必须保留原 key；保留 @用户名、URL、#标签、产品名、模型名和代码；不要解释、不要 Markdown，"
            "只输出一个合法 JSON 对象。\nINPUT:\n"
            + json.dumps(remaining, ensure_ascii=False)
        )
        try:
            completed = subprocess.run(
                CODEX_EXEC_COMMAND,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=360,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
        else:
            if completed.returncode == 0:
                try:
                    translated = parse_translation_json(completed.stdout)
                except ValueError as exc:
                    last_error = str(exc)
                else:
                    valid = {key: translated[key] for key in remaining if translated.get(key)}
                    if valid:
                        collected.update(valid)
                        remaining = {key: text for key, text in remaining.items() if key not in valid}
                        if not remaining:
                            return collected, ""
                        last_error = f"Codex omitted {len(remaining)} translation keys"
                    else:
                        last_error = "Codex returned no matching translation keys"
            else:
                last_error = redact(completed.stderr or completed.stdout or f"exit {completed.returncode}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    if len(remaining) > 1:
        items = list(remaining.items())
        split_size = max(1, len(items) // 2)
        split_errors: list[str] = []
        for index in range(0, len(items), split_size):
            translated, error = translate_batch(dict(items[index : index + split_size]), retries)
            collected.update(translated)
            if error:
                split_errors.append(error)
        unresolved = set(batch) - set(collected)
        return collected, "; ".join(split_errors) if unresolved else ""
    return collected, last_error


def translate_posts(
    posts: list[dict[str, Any]],
    cache_path: Path,
    batch_size: int,
    workers: int,
    retries: int,
) -> dict[str, Any]:
    targets = collect_translation_targets(posts)
    cache = load_translation_cache(cache_path)
    cached_translations = cache["translations"]
    pending: dict[str, str] = {}
    cache_hits = 0

    for key, target in targets.items():
        entry = cached_translations.get(key)
        translation = (
            entry.get("zh")
            if isinstance(entry, dict)
            and entry.get("source") == target["text"]
            and entry.get("promptVersion") == TRANSLATION_PROMPT_VERSION
            else ""
        )
        if translation:
            cache_hits += 1
            for container, field in target["destinations"]:
                container[field] = translation
        else:
            pending[key] = target["text"]

    batches = [
        dict(list(pending.items())[index : index + max(1, batch_size)])
        for index in range(0, len(pending), max(1, batch_size))
    ]
    translated_count = 0
    errors: list[str] = []
    if batches:
        print(f"Translating {len(pending)} unique texts with Codex in {len(batches)} batches...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            future_map = {pool.submit(translate_batch, batch, retries): batch for batch in batches}
            completed_count = 0
            for future in concurrent.futures.as_completed(future_map):
                batch = future_map[future]
                translated, error = future.result()
                completed_count += 1
                print(f"[translate {completed_count:02d}/{len(batches):02d}] {len(translated)}/{len(batch)} texts", flush=True)
                if error:
                    errors.append(error)
                for key, translation in translated.items():
                    target = targets[key]
                    cached_translations[key] = {
                        "source": target["text"],
                        "zh": translation,
                        "promptVersion": TRANSLATION_PROMPT_VERSION,
                    }
                    for container, field in target["destinations"]:
                        container[field] = translation
                    translated_count += 1

    cache["version"] = 2
    cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    completed = cache_hits + translated_count
    return {
        "enabled": True,
        "backend": "codex exec",
        "promptVersion": TRANSLATION_PROMPT_VERSION,
        "eligibleTexts": len(targets),
        "cacheHits": cache_hits,
        "translatedNow": translated_count,
        "failed": max(0, len(targets) - completed),
        "coverage": round(completed / len(targets), 4) if targets else 1.0,
        "errors": errors[:5],
        "cache": str(cache_path),
    }


def safe(value: Any) -> str:
    normalized = "\n".join(line.rstrip() for line in str(value or "").splitlines())
    return html.escape(normalized, quote=True)


def render_media(media: Any) -> str:
    if not isinstance(media, list) or not media:
        return ""
    items = []
    for entry in media[:4]:
        if not isinstance(entry, dict):
            continue
        media_type = str(entry.get("type") or "photo")
        url = entry.get("url") or entry.get("previewUrl") or entry.get("preview_image_url")
        if not url:
            continue
        label = "VIDEO" if media_type in {"video", "animated_gif"} else "IMAGE"
        items.append(
            f'<a class="media-item" href="{safe(url)}" target="_blank" rel="noreferrer">'
            f'<img loading="lazy" src="{safe(url)}" alt="X post media"><span>{label}</span></a>'
        )
    return f'<div class="media-grid media-grid--{min(len(items), 4)}">{"".join(items)}</div>' if items else ""


def render_bilingual(source: Any, translation: Any, class_name: str) -> str:
    source_text = str(source or "").strip()
    translation_text = str(translation or "").strip()
    if not source_text:
        return ""
    if translation_text:
        return (
            f'<p class="{safe(class_name)} original" lang="auto">{safe(source_text)}</p>'
            f'<p class="{safe(class_name)} translation" lang="zh-CN">{safe(translation_text)}</p>'
        )
    return f'<p class="{safe(class_name)} original source-only" lang="auto">{safe(source_text)}</p>'


def render_article(article: Any) -> str:
    if not isinstance(article, dict) or not article.get("title"):
        return ""
    title = str(article.get("title") or "")
    title_zh = str(article.get("titleZh") or "")
    if title_zh:
        title_html = f'<strong class="original" lang="auto">{safe(title)}</strong><strong class="translation" lang="zh-CN">{safe(title_zh)}</strong>'
    else:
        title_html = f'<strong class="original source-only" lang="auto">{safe(title)}</strong>'
    preview_html = render_bilingual(article.get("previewText"), article.get("previewTextZh"), "article-text")
    return f'<div class="article">{title_html}{preview_html}</div>'


def render_quote(quote: Any) -> str:
    if not isinstance(quote, dict):
        return ""
    author = quote.get("author") or {}
    username = author.get("username") or "unknown"
    name = author.get("name") or username
    quote_id = quote.get("id") or ""
    url = f"https://x.com/{username}/status/{quote_id}" if quote_id else "#"
    profile_image = author.get("profileImageUrl")
    quote_avatar = (
        f'<img src="{safe(profile_image)}" alt="{safe(name)} avatar" loading="lazy">'
        if profile_image else f'<span>{safe(str(name)[:1].upper())}</span>'
    )
    return (
        f'<div class="quote">'
        f'<div class="quote__author"><div class="quote-avatar">{quote_avatar}</div><div><strong>{safe(name)}</strong><span>@{safe(username)}</span></div></div>'
        f'{render_bilingual(quote.get("text"), quote.get("translationZh"), "quote-text")}'
        f'{render_article(quote.get("article"))}{render_media(quote.get("media"))}'
        f'<a class="quote-link" href="{safe(url)}" target="_blank" rel="noreferrer">查看引用动态 ↗</a></div>'
    )


def render_post(post: dict[str, Any]) -> str:
    expert = post["expert"]
    author = post.get("author") or {}
    username = author.get("username") or expert["handle"]
    initials = "".join(part[0] for part in expert["name"].split()[:2]).upper() or expert["handle"][:2].upper()
    profile_image = author.get("profileImageUrl")
    avatar_html = f'<img src="{safe(profile_image)}" alt="{safe(expert["name"])} avatar" loading="lazy">' if profile_image else safe(initials)
    engagement = (
        f'<span>♡ {int(post.get("likeCount") or 0):,}</span>'
        f'<span>↻ {int(post.get("retweetCount") or 0):,}</span>'
        f'<span>↩ {int(post.get("replyCount") or 0):,}</span>'
    )
    return f"""
      <article class="signal-card" data-theme="{safe(post['themeId'])}" data-priority="{safe(expert['priority'])}" data-expert="{safe(expert['handle'].casefold())}" data-top-story="{str(bool(post.get('isTopStory'))).lower()}">
        <div class="card-top">
          <div class="avatar">{avatar_html}</div>
          <div class="identity"><strong>{safe(expert['name'])}</strong><span>@{safe(username)} · {safe(expert['role'])}</span></div>
          <div class="score">{post['signalScore']}<small>signal</small></div>
        </div>
        <div class="meta"><span class="priority">{safe(expert['priority'])}</span><span>{safe(expert['domain'])}</span><time>{safe(post['createdAtLocal'])}</time></div>
        {render_bilingual(post.get('text'), post.get('translationZh'), 'post-text')}
        {render_article(post.get('article'))}
        {render_media(post.get('media'))}
        {render_quote(post.get('quotedTweet'))}
        <div class="card-bottom"><div class="engagement">{engagement}</div><a href="{safe(post['url'])}" target="_blank" rel="noreferrer">Open on X ↗</a></div>
      </article>
    """


def top_story_author_key(post: dict[str, Any]) -> str:
    expert = post.get("expert") or {}
    author = post.get("author") or {}
    return str(
        expert.get("handle")
        or author.get("username")
        or post.get("id")
        or "unknown"
    ).casefold()


def select_diverse_top_stories(posts: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    """Select the strongest eligible stories while maximizing author diversity."""
    candidates = sorted(
        (post for post in posts if post.get("topStoryEligible")),
        key=lambda post: (
            int(post.get("topStoryScore") or 0),
            int(post.get("signalScore") or 0),
            str(post.get("createdAtIso") or ""),
        ),
        reverse=True,
    )
    target = min(max(0, limit), len(candidates))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    seen_authors: set[str] = set()

    for post in candidates:
        author_key = top_story_author_key(post)
        if author_key in seen_authors:
            continue
        selected.append(post)
        selected_ids.add(str(post.get("id") or ""))
        seen_authors.add(author_key)
        if len(selected) == target:
            return selected

    for post in candidates:
        post_id = str(post.get("id") or "")
        if post_id in selected_ids:
            continue
        selected.append(post)
        selected_ids.add(post_id)
        if len(selected) == target:
            break
    return selected


def order_posts_for_report(experts: list[Expert], posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for post in posts:
        post["isTopStory"] = False
    top_stories = select_diverse_top_stories(posts, limit=3)
    top_ids = {str(post.get("id") or "") for post in top_stories}
    for post in top_stories:
        post["isTopStory"] = True

    remaining_by_expert: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        if str(post.get("id") or "") not in top_ids:
            remaining_by_expert[post["expert"]["handle"].casefold()].append(post)
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    expert_order = {expert.handle.casefold(): index for index, expert in enumerate(experts)}
    active_experts = sorted(
        (expert for expert in experts if expert.handle.casefold() in remaining_by_expert),
        key=lambda expert: (
            priority_rank.get(expert.priority, 9),
            strategic_org_rank(expert),
            expert_order[expert.handle.casefold()],
        ),
    )
    ordered_remaining: list[dict[str, Any]] = []
    for expert in active_experts:
        ordered_remaining.extend(remaining_by_expert[expert.handle.casefold()])
    return top_stories + ordered_remaining


def render_report(
    experts: list[Expert],
    posts: list[dict[str, Any]],
    results: list[dict[str, Any]],
    now: datetime,
    cutoff: datetime,
) -> str:
    active_handles = {post["expert"]["handle"].casefold() for post in posts}
    failures = [result for result in results if not result["ok"]]
    failed_accounts = sum(len(result.get("experts", [])) for result in failures)
    cards = "".join(render_post(post) for post in posts)
    if not cards:
        cards = '<div class="empty">最近 23 小时没有抓取到符合条件的公开动态。</div>'
    failure_note = ""
    if failures:
        failure_note = f'<div class="notice">有 {failed_accounts} 个账号本轮抓取失败，详情见 data/run-report.json；其他账号的日报已正常生成。</div>'
    generated = now.astimezone(SHANGHAI)
    rendered = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>硅谷 AI 原声 · {generated:%Y-%m-%d}</title>
  <style>
    :root{{--bg:#f4f6f8;--surface:#fff;--text:#16181c;--muted:#65717e;--line:#dfe4e9;--accent:#0066cc;--green:#117a62;--shadow:0 16px 42px rgba(18,28,38,.08);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
    *{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 15% 0,#e8f2ff 0,transparent 27%),var(--bg);color:var(--text)}} a{{color:inherit;text-decoration:none}} button{{font:inherit}}
    .shell{{width:min(1500px,calc(100% - 28px));margin:0 auto;padding:14px 0 40px}}
    .hero{{display:grid;grid-template-columns:minmax(250px,1fr) auto;align-items:center;gap:12px;padding:15px 18px;border:1px solid rgba(255,255,255,.75);border-radius:16px;background:rgba(255,255,255,.88);box-shadow:var(--shadow);backdrop-filter:blur(18px)}}
    h1{{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin:0;font-size:clamp(28px,3.4vw,44px);line-height:1;letter-spacing:-.05em}} .report-date{{color:var(--green);font-size:clamp(10px,1vw,13px);font-weight:900;letter-spacing:.08em;white-space:nowrap}}
    .metrics{{display:grid;grid-template-columns:repeat(3,minmax(62px,1fr));gap:6px;align-content:start}} .metric{{padding:8px 10px;border:1px solid var(--line);border-radius:9px;background:#fff}} .metric strong{{display:block;font-size:19px;line-height:1}} .metric span{{display:block;margin-top:3px;color:var(--muted);font-size:8px;font-weight:820;white-space:nowrap}}
    .notice{{margin-top:12px;padding:11px 14px;border:1px solid #e1b866;border-radius:12px;background:#fff8e8;color:#7a5612;font-size:12px}}
    .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:14px;align-items:start}} .signal-card{{min-width:0;padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 9px 26px rgba(18,28,38,.045)}}
    .card-top{{display:grid;grid-template-columns:46px minmax(0,1fr) auto;align-items:center;gap:10px}} .avatar{{display:grid;width:46px;height:46px;overflow:hidden;place-items:center;border:1px solid #d9e0e7;border-radius:999px;background:linear-gradient(135deg,#111827,#46627d);color:#fff;font-size:12px;font-weight:900}} .avatar img{{width:100%;height:100%;object-fit:cover;display:block}} .identity{{display:grid;gap:3px;min-width:0}} .identity strong,.identity span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .identity strong{{font-size:14px}} .identity span{{color:var(--muted);font-size:11px}}
    .score{{display:grid;justify-items:center;min-width:40px;padding:5px 6px;border:1px solid #e3ebe8;border-radius:8px;background:#f4f8f6;color:#527267;font-size:15px;font-weight:820;line-height:1}} .score small{{margin-top:2px;color:#71877f;font-size:7px;letter-spacing:.06em;text-transform:uppercase}}
    .meta{{display:flex;align-items:center;gap:6px;margin:11px 0 9px;color:var(--muted);font-size:10.5px;font-weight:750}} .meta span:not(.priority){{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .meta time{{margin-left:auto;white-space:nowrap}} .priority{{padding:3px 6px;border-radius:999px;background:#111827;color:#fff;font-size:9px}}
    .post-text{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.58}} .post-text.original{{font-size:16px;font-weight:570;color:#20252b}} .post-text.translation{{margin-top:8px;color:#66727f;font-size:13px;font-weight:470;line-height:1.62}} .article .original+.translation{{margin-top:2px;color:#65717e;font-size:11px;font-weight:650}} .quote,.article{{display:grid;gap:6px;margin-top:10px;padding:11px;border:1px solid var(--line);border-radius:12px;background:#f7f9fb}} .quote__author{{display:flex;align-items:center;gap:7px;font-size:11px}} .quote__author>div:last-child{{display:grid;gap:1px}} .quote__author span{{color:var(--muted)}} .quote-avatar{{display:grid;width:28px;height:28px;overflow:hidden;place-items:center;border:1px solid var(--line);border-radius:999px;background:#dfe6ed;color:#52606d;font-size:10px;font-weight:900}} .quote-avatar img{{width:100%;height:100%;object-fit:cover}} .quote p,.article p{{margin:0;color:#4f5a66;font-size:12px;line-height:1.48;white-space:pre-wrap}} .article strong{{font-size:13px}} .article strong.original{{font-size:13.5px}} .quote-text.original{{font-size:12.5px;color:#36414d}} .quote-text.translation{{font-size:11.5px;color:#6a7682}} .quote-link{{justify-self:start;color:var(--accent);font-size:10px;font-weight:850}}
    .media-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:3px;margin-top:10px;overflow:hidden;border-radius:12px}} .media-grid--1{{grid-template-columns:1fr}} .media-item{{position:relative;min-height:150px;background:#e8edf2}} .media-item img{{width:100%;height:100%;max-height:330px;object-fit:cover;display:block}} .media-item span{{position:absolute;right:7px;bottom:7px;padding:4px 6px;border-radius:6px;background:rgba(0,0,0,.68);color:#fff;font-size:8px;font-weight:900}}
    .card-bottom{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px;padding-top:10px;border-top:1px solid #edf0f3}} .engagement{{display:flex;gap:10px;color:var(--muted);font-size:10.5px;font-weight:750}} .card-bottom>a{{color:var(--accent);font-size:11px;font-weight:850}} .empty{{grid-column:1/-1;padding:70px;text-align:center;border:1px dashed #cdd5dd;border-radius:16px;background:#fff;color:var(--muted)}}
    footer{{padding:26px 4px 0;color:var(--muted);font-size:11px;text-align:center}}
    @media(max-width:900px){{.hero{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}}} @media(max-width:560px){{.shell{{width:min(100% - 16px,1500px);padding-top:7px}}.hero{{gap:10px;padding:13px 14px;border-radius:15px}}h1{{font-size:28px}}.metrics{{grid-template-columns:repeat(3,minmax(0,1fr))}}.metric{{padding:7px 9px}}.metric strong{{font-size:18px}}.signal-card{{padding:13px}}.post-text.original{{font-size:15px}}.post-text.translation{{font-size:12.5px}}}}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <h1>硅谷 AI 原声 <span class="report-date">· {generated:%Y-%m-%d}</span></h1>
      <div class="metrics"><div class="metric"><strong>{len(experts)}</strong><span>监控专家</span></div><div class="metric"><strong>{len(active_handles)}</strong><span>活跃专家</span></div><div class="metric"><strong>{len(posts)}</strong><span>精选原文</span></div></div>
    </header>
    {failure_note}
    <main class="grid">{cards}</main>
    <footer>Generated {generated:%Y-%m-%d %H:%M:%S} Asia/Shanghai · Read-only X ingestion via Bird · Translation via Codex</footer>
  </div>
</body>
</html>"""
    return "\n".join(line.rstrip() for line in rendered.splitlines()) + "\n"


def rebuild_from_data(args: argparse.Namespace, experts: list[Expert]) -> int:
    payload = json.loads(args.reuse_data.read_text(encoding="utf-8"))
    posts = payload.get("posts", [])
    if not isinstance(posts, list):
        raise RuntimeError(f"Invalid posts array in {args.reuse_data}")
    posts = [post for post in posts if isinstance(post, dict)]
    original_post_count = len(posts)
    selected_ids = {str(post.get("id") or "") for post in posts}
    posts = [post for post in posts if not is_redundant_nontechnical_wrapper(post, selected_ids)]
    removed_redundant_wrappers = original_post_count - len(posts)
    recruitment_candidate_count = len(posts)
    posts = [post for post in posts if not is_recruitment_post(post)]
    removed_recruitment = recruitment_candidate_count - len(posts)
    technical_candidate_count = len(posts)
    posts = [post for post in posts if is_technical_post(post)]
    removed_nontechnical = technical_candidate_count - len(posts)
    experts_by_handle = {expert.handle.casefold(): expert for expert in experts}
    for post in posts:
        handle = str((post.get("expert") or {}).get("handle") or "").casefold()
        expert = experts_by_handle.get(handle)
        if expert:
            post["signalScore"] = signal_score(post, expert)
            attach_editorial_rank(post, expert)
        created_at = parse_created_at(str(post.get("createdAtIso") or post.get("createdAt") or ""))
        if created_at:
            created_at = created_at.astimezone(timezone.utc)
            post["createdAtIso"] = created_at.isoformat()
            post["createdAtBeijing"] = created_at.astimezone(SHANGHAI).isoformat()
            post["createdAtLocal"] = created_at.astimezone(SHANGHAI).strftime("%m-%d %H:%M 北京")
    posts = order_posts_for_report(experts, posts)
    now = datetime.fromisoformat(str(payload["generatedAt"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    cutoff = datetime.fromisoformat(str(payload["windowStart"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    if args.avatars:
        avatar_cache = args.avatar_cache or (args.output_root / "avatar-cache.json")
        avatar_report = hydrate_post_avatars(posts, avatar_cache, args.cookie_source, args.avatar_workers, args.retries)
    else:
        avatar_report = {"enabled": False, "authors": 0, "postsWithAvatar": 0, "coverage": 0.0, "errors": []}
    if args.translate:
        translation_cache = args.translation_cache or (args.output_root / "translation-cache.json")
        translation_report = translate_posts(
            posts,
            translation_cache,
            args.translation_batch_size,
            args.translation_workers,
            args.translation_retries,
        )
    else:
        translation_report = {"enabled": False, "eligibleTexts": 0, "cacheHits": 0, "translatedNow": 0, "failed": 0, "coverage": 0.0, "errors": []}
    local_date = now.astimezone(SHANGHAI).strftime("%Y%m%d")
    output_dir = args.output_root / local_date
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload["posts"] = posts
    payload["fetchStartedAt"] = str(payload.get("fetchStartedAt") or payload.get("generatedAt"))
    payload["translation"] = translation_report
    payload["avatars"] = avatar_report
    results = [{
        "label": "reused-data",
        "ok": True,
        "experts": [dataclasses.asdict(expert) for expert in experts],
        "tweets": [],
        "attempts": 0,
        "elapsedSeconds": 0,
    }]
    report_path = data_dir / "run-report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    except json.JSONDecodeError:
        report = {}
    report.update({
        "generatedAt": now.isoformat(),
        "fetchStartedAt": str(payload.get("fetchStartedAt") or now.isoformat()),
        "windowStart": cutoff.isoformat(),
        "accountsRequested": int(report.get("accountsRequested") or len(experts)),
        "accountsSucceeded": int(report.get("accountsSucceeded") or len(experts)),
        "accountsFailed": int(report.get("accountsFailed") or 0),
        "postsSelected": len(posts),
        "topStories": [
            {
                "id": post.get("id"),
                "author": (post.get("expert") or {}).get("handle"),
                "category": post.get("topStoryCategory"),
                "editorialScore": post.get("topStoryScore"),
            }
            for post in posts[:3]
            if post.get("isTopStory")
        ],
        "translation": translation_report,
        "avatars": avatar_report,
        "rebuiltFromData": str(args.reuse_data),
        "rebuildDroppedRecruitment": removed_recruitment,
        "rebuildDroppedNonTechnical": removed_nontechnical + removed_redundant_wrappers,
    })
    (data_dir / "posts.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "index.html").write_text(render_report(experts, posts, results, now, cutoff), encoding="utf-8")
    print(json.dumps(report | {"output": str(output_dir / "index.html")}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    if not math.isclose(args.hours, 23.0):
        raise RuntimeError("AI V-Radar requires an exact 23-hour window")
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=SHANGHAI)
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)
    experts = load_experts(args.watchlist)
    if args.limit > 0:
        experts = experts[: args.limit]
    if args.reuse_data:
        return rebuild_from_data(args, experts)

    print(f"Fetching {len(experts)} X accounts with Bird ({args.fetch_mode})...", flush=True)
    results: list[dict[str, Any]] = []
    if args.fetch_mode == "search":
        batch_size = max(1, args.search_batch_size)
        work_items: list[Any] = [
            experts[index : index + batch_size]
            for index in range(0, len(experts), batch_size)
        ]
    else:
        work_items = experts
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        if args.fetch_mode == "search":
            future_map = {
                pool.submit(
                    fetch_search_batch,
                    batch,
                    cutoff,
                    args.cookie_source,
                    args.search_max_pages,
                    args.retries,
                ): batch
                for batch in work_items
            }
        else:
            future_map = {
                pool.submit(fetch_expert, expert, args.count_per_user, args.cookie_source, args.retries): expert
                for expert in work_items
            }
        completed_count = 0
        for future in concurrent.futures.as_completed(future_map):
            result = future.result()
            results.append(result)
            completed_count += 1
            status = "ok" if result["ok"] else "failed"
            tweet_count = len(result.get("tweets", []))
            item = future_map[future]
            label = result["label"] if args.fetch_mode == "timeline" else f"{len(item)} accounts"
            print(f"[{completed_count:02d}/{len(work_items):02d}] {label}: {status} ({tweet_count} fetched)", flush=True)

    results.sort(key=lambda item: item["label"].casefold())
    posts, dropped = normalize_posts(results, experts, cutoff, now, args.max_posts)
    posts = order_posts_for_report(experts, posts)
    if args.avatars:
        avatar_cache = args.avatar_cache or (args.output_root / "avatar-cache.json")
        avatar_report = hydrate_post_avatars(posts, avatar_cache, args.cookie_source, args.avatar_workers, args.retries)
    else:
        avatar_report = {"enabled": False, "authors": 0, "postsWithAvatar": 0, "coverage": 0.0, "errors": []}
    if args.translate:
        translation_cache = args.translation_cache or (args.output_root / "translation-cache.json")
        translation_report = translate_posts(
            posts,
            translation_cache,
            args.translation_batch_size,
            args.translation_workers,
            args.translation_retries,
        )
    else:
        translation_report = {
            "enabled": False,
            "eligibleTexts": 0,
            "cacheHits": 0,
            "translatedNow": 0,
            "failed": 0,
            "coverage": 0.0,
            "errors": [],
        }
    local_date = now.astimezone(SHANGHAI).strftime("%Y%m%d")
    output_dir = args.output_root / local_date
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    raw_payload = {
        "generatedAt": now.isoformat(),
        "fetchStartedAt": now.isoformat(),
        "windowStart": cutoff.isoformat(),
        "windowHours": args.hours,
        "experts": [dataclasses.asdict(expert) for expert in experts],
        "posts": posts,
        "translation": translation_report,
        "avatars": avatar_report,
    }
    report = {
        "generatedAt": now.isoformat(),
        "fetchStartedAt": now.isoformat(),
        "windowStart": cutoff.isoformat(),
        "accountsRequested": len(experts),
        "fetchMode": args.fetch_mode,
        "accountsSucceeded": sum(len(result.get("experts", [])) for result in results if result["ok"]),
        "accountsFailed": sum(len(result.get("experts", [])) for result in results if not result["ok"]),
        "postsSelected": len(posts),
        "topStories": [
            {
                "id": post.get("id"),
                "author": (post.get("expert") or {}).get("handle"),
                "category": post.get("topStoryCategory"),
                "editorialScore": post.get("topStoryScore"),
            }
            for post in posts[:3]
            if post.get("isTopStory")
        ],
        "translation": translation_report,
        "avatars": avatar_report,
        "dropped": dict(dropped),
        "failures": [
            {"handles": [expert["handle"] for expert in result.get("experts", [])], "error": result.get("error", "unknown")}
            for result in results
            if not result["ok"]
        ],
        "fetches": [
            {
                "handles": [expert["handle"] for expert in result.get("experts", [])],
                "ok": result["ok"],
                "fetched": len(result.get("tweets", [])),
                "attempts": result["attempts"],
                "elapsedSeconds": result["elapsedSeconds"],
            }
            for result in results
        ],
    }
    (data_dir / "posts.json").write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "run-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "index.html").write_text(render_report(experts, posts, results, now, cutoff), encoding="utf-8")

    print(json.dumps(report | {"output": str(output_dir / "index.html")}, ensure_ascii=False, indent=2))
    return 0 if report["accountsSucceeded"] else 2


if __name__ == "__main__":
    sys.exit(main())
