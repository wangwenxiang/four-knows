from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from .models import Tweet
from .scoring import categorize, score_tweet


def write_normalized_jsonl(path: Path, tweets: list[Tweet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for tweet in tweets:
            item = {
                "id": tweet.id,
                "author_handle": tweet.author_handle,
                "author_name": tweet.author_name,
                "text": tweet.text,
                "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                "url": tweet.url,
                "like_count": tweet.like_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count,
                "quote_count": tweet.quote_count,
                "view_count": tweet.view_count,
                "score": score_tweet(tweet),
                "category": categorize(tweet),
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def render_markdown(tweets: list[Tweet], report_date: date, top_n: int = 25, min_score: float = 0) -> str:
    scored = sorted(
        ((score_tweet(tweet), tweet) for tweet in tweets),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = [(score, tweet) for score, tweet in scored if score >= min_score][:top_n]

    lines: list[str] = []
    lines.append(f"# AI 技术专家 X 日报 - {report_date.isoformat()}")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"覆盖推文：{len(tweets)} 条；入选高信号：{len(selected)} 条")
    lines.append("")

    lines.append("## 今日要点")
    if selected:
        for score, tweet in selected[:5]:
            lines.append(f"- {brief(tweet.text)}（@{tweet.author_handle}，{score:.1f}）")
    else:
        lines.append("- 暂无可入选推文。")
    lines.append("")

    grouped: dict[str, list[tuple[float, Tweet]]] = defaultdict(list)
    for score, tweet in selected:
        grouped[categorize(tweet)].append((score, tweet))

    lines.append("## 分主题观察")
    for category in ("模型与论文", "Agent 与产品", "工程与基础设施", "开源与数据", "产业与观点", "其他高信号"):
        items = grouped.get(category, [])
        if not items:
            continue
        lines.append(f"### {category}")
        for score, tweet in items[:8]:
            lines.append(format_tweet_bullet(tweet, score))
        lines.append("")

    author_counter = Counter(tweet.author_handle for _, tweet in selected)
    lines.append("## 活跃账号")
    if author_counter:
        lines.append(", ".join(f"@{handle} {count} 条" for handle, count in author_counter.most_common(10)))
    else:
        lines.append("暂无。")
    lines.append("")

    lines.append("## 全量高信号链接")
    for score, tweet in selected:
        link = tweet.url or f"https://x.com/{tweet.author_handle}/status/{tweet.id}"
        lines.append(f"- @{tweet.author_handle} [{tweet.id}]({link}) score={score:.1f}")
    lines.append("")

    return "\n".join(lines)


def format_tweet_bullet(tweet: Tweet, score: float) -> str:
    link = tweet.url or f"https://x.com/{tweet.author_handle}/status/{tweet.id}"
    metrics = []
    if tweet.like_count:
        metrics.append(f"{tweet.like_count} likes")
    if tweet.retweet_count:
        metrics.append(f"{tweet.retweet_count} RT")
    metric_text = f"；{', '.join(metrics)}" if metrics else ""
    return f"- **@{tweet.author_handle}**：{brief(tweet.text, 180)} [原文]({link})（score {score:.1f}{metric_text}）"


def brief(text: str, max_chars: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "..."
