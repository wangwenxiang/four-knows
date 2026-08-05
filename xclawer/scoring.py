from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import Tweet


KEYWORD_WEIGHTS = {
    "paper": 5,
    "arxiv": 5,
    "model": 4,
    "llm": 4,
    "agent": 4,
    "benchmark": 4,
    "eval": 4,
    "open source": 4,
    "github": 3,
    "release": 3,
    "dataset": 3,
    "inference": 3,
    "training": 3,
    "reasoning": 3,
    "multimodal": 3,
    "gpu": 2,
    "cuda": 2,
    "robot": 2,
    "voice": 2,
    "video": 2,
    "research": 2,
}

CATEGORY_KEYWORDS = {
    "模型与论文": ("paper", "arxiv", "model", "llm", "reasoning", "multimodal", "benchmark"),
    "Agent 与产品": ("agent", "workflow", "tool", "product", "app", "copilot"),
    "工程与基础设施": ("inference", "training", "gpu", "cuda", "serving", "latency", "infra"),
    "开源与数据": ("open source", "github", "dataset", "license", "weights"),
    "产业与观点": ("startup", "funding", "policy", "regulation", "market", "strategy"),
}


def score_tweet(tweet: Tweet, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    score = 0.0

    if tweet.created_at is not None:
        age_hours = max((now - tweet.created_at.astimezone(timezone.utc)).total_seconds() / 3600, 0)
        score += max(0, 18 - age_hours / 2)
    else:
        score += 4

    score += math.log1p(tweet.engagement) * 4
    score += math.log1p(tweet.view_count) * 0.8 if tweet.view_count else 0

    lower_text = tweet.text.lower()
    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword in lower_text:
            score += weight

    if tweet.is_retweet:
        score *= 0.65

    if len(tweet.text) < 35:
        score *= 0.8

    return round(score, 2)


def categorize(tweet: Tweet) -> str:
    lower_text = tweet.text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            return category
    return "其他高信号"
