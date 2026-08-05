from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import Tweet


TEXT_KEYS = ("text", "full_text", "fullText", "body")
ID_KEYS = ("id", "id_str", "tweet_id", "tweetId", "rest_id", "conversation_id_str")
TIME_KEYS = ("created_at", "createdAt", "time", "timestamp")


def normalize_tweets(payload: Any, default_author: str = "") -> list[Tweet]:
    tweets: list[Tweet] = []
    seen_payload_ids: set[int] = set()
    for candidate in _walk_dicts(payload):
        marker = id(candidate)
        if marker in seen_payload_ids:
            continue
        seen_payload_ids.add(marker)

        tweet = _dict_to_tweet(candidate, default_author=default_author)
        if tweet is not None:
            tweets.append(tweet)
    return dedupe_tweets(tweets)


def dedupe_tweets(tweets: Iterable[Tweet]) -> list[Tweet]:
    seen: set[str] = set()
    result: list[Tweet] = []
    for tweet in tweets:
        key = tweet.id or f"{tweet.author_handle}:{tweet.text[:80]}"
        if key in seen:
            continue
        seen.add(key)
        result.append(tweet)
    return result


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_dicts(item)


def _dict_to_tweet(data: dict[str, Any], default_author: str = "") -> Tweet | None:
    text = _first_text(data)
    tweet_id = _first_scalar(data, ID_KEYS)

    legacy = data.get("legacy")
    if isinstance(legacy, dict):
        text = text or _first_text(legacy)
        tweet_id = tweet_id or _first_scalar(legacy, ID_KEYS)

    if not text or not tweet_id:
        return None

    author_handle = _author_handle(data) or default_author.lstrip("@")
    if not author_handle:
        author_handle = _author_from_url(str(data.get("url", ""))) or ""

    created_at = _parse_datetime(_first_scalar(data, TIME_KEYS) or (legacy and _first_scalar(legacy, TIME_KEYS)))
    url = str(data.get("url") or data.get("tweetUrl") or "")
    if not url and author_handle and tweet_id:
        url = f"https://x.com/{author_handle}/status/{tweet_id}"

    text = _clean_text(str(text))
    return Tweet(
        id=str(tweet_id),
        author_handle=author_handle,
        author_name=_author_name(data),
        text=text,
        created_at=created_at,
        url=url,
        like_count=_metric(data, legacy, ("like_count", "favorite_count", "likes", "favoriteCount")),
        retweet_count=_metric(data, legacy, ("retweet_count", "retweets", "retweetCount")),
        reply_count=_metric(data, legacy, ("reply_count", "replies", "replyCount")),
        quote_count=_metric(data, legacy, ("quote_count", "quotes", "quoteCount")),
        view_count=_metric(data, legacy, ("view_count", "views", "viewCount")),
        is_retweet=str(text).startswith("RT @") or bool(data.get("retweeted")),
        raw=data,
    )


def _first_text(data: dict[str, Any]) -> str:
    for key in TEXT_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value

    note = data.get("note_tweet") or data.get("noteTweet")
    if isinstance(note, dict):
        text = _first_text(note)
        if text:
            return text
        result = note.get("result")
        if isinstance(result, dict):
            return _first_text(result)
    return ""


def _first_scalar(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value)
    return ""


def _author_handle(data: dict[str, Any]) -> str:
    for key in ("author_handle", "authorHandle", "screen_name", "username", "handle"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.lstrip("@")

    user = data.get("user") or data.get("author") or data.get("core")
    if isinstance(user, dict):
        nested = user.get("user_results") if "user_results" in user else user
        if isinstance(nested, dict):
            result = nested.get("result") if "result" in nested else nested
            if isinstance(result, dict):
                legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else result
                handle = _first_scalar(legacy, ("screen_name", "username", "handle"))
                if handle:
                    return handle.lstrip("@")
    return ""


def _author_name(data: dict[str, Any]) -> str:
    for key in ("author_name", "authorName", "name", "displayName"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _metric(data: dict[str, Any], legacy: Any, keys: tuple[str, ...]) -> int:
    for source in (data, legacy if isinstance(legacy, dict) else {}):
        for key in keys:
            value = source.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return 0


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _author_from_url(url: str) -> str:
    match = re.search(r"x\.com/([^/]+)/status/", url)
    return match.group(1) if match else ""


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
