from __future__ import annotations

import html
import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/active-last-day-search-2026-06-30.json"
RAW_SEARCH_DIR = ROOT / "data/raw-search/2026-06-30"
ACCOUNTS = ROOT / "config/accounts.from-html.json"
OUT = ROOT / "report-app/src/data/daily-report.json"
AVATAR_DIR = ROOT / "report-app/public/avatars"
MEDIA_DIR = ROOT / "report-app/public/tweet-media"
LEGACY_SCRIPT = ROOT / "scripts/build_visual_report.py"


THEMES = {
    "agent-workflow": {
        "title": "Agent 工作流",
        "shortLabel": "Agent",
        "evidenceLabel": "模型路由 / 子 Agent / 上下文缓存",
    },
    "memory-rag": {
        "title": "记忆与检索",
        "shortLabel": "Memory",
        "evidenceLabel": "Wiki Memory / Retrieval Harness / 文档工具",
    },
    "eval-quality": {
        "title": "评测与质量",
        "shortLabel": "Evals",
        "evidenceLabel": "Trace Judge / 产品可评估性",
    },
    "creative-ai": {
        "title": "创意与视频",
        "shortLabel": "Creative",
        "evidenceLabel": "Runway 文化 / 技术 / 使命",
    },
}


SIGNAL_DETAILS = {
    "2071963841009942671": {
        "translation": "我们看到一种常见的、属于记忆能力一部分的模式：Wiki Memory。例子包括 DeepWiki（Cognition）、AutoWiki（FactoryAI）和 LLM Wiki（Karpathy）。",
    },
    "2071737452323303750": {
        "translation": "这是一个围绕模型路由和子 Agent 委派的好想法，同时确保所有 Agent 都能命中累积上下文缓存。这很合理：你希望所有子 Agent 也能使用缓存中的累积上下文。",
    },
    "2071729856900215261": {
        "translation": "我们很高兴在 LlamaParse 中推出 Retrieval Harness，它是 2026 版的文档 RAG。通用 Agent 需要合适的工具，才能在任意数据语料中可扩展地搜索和阅读，从 10 个文档到 100 万以上文档都要覆盖。Retrieval Harness 提供多种工具：1. Hybrid Retrieval：结合向量搜索和关键词搜索，并让 Agent 设置 alpha 值切换两者；2. List Files：可扩展版的 ls，用于列出索引内文件；3. File Grep：在指定文件内做正则搜索；4. File Read：让 Agent 读取现有文档的某个片段。Agent 可以按任意顺序组合这些工具，以完成从简单到困难的多种任务。",
    },
    "2071718682250928421": {
        "translation": "模型路由是热门话题，但给 coding agent 做路由有两个挑战：1. 即使不同模型都能完成任务，它们在行为和风格上仍有细微差异，不能完全互换；2. 初始 agent prompt 不足以判断任务难度。'修复 xyz bug' 可能是一行边界条件，也可能需要重构整个产品，必须真正调查代码后才知道。怎么解决？你需要能覆盖风格和行为的评测，而不只是通过/失败；也需要 agent 能动态更新并重新路由。我们构建 Devin Fusion 时考虑了这两点，发现它在保持前沿智能体验的同时降低了 30%-40% 成本。",
    },
    "2071713645927784543": {
        "translation": "Hamel 写了一篇不错的博客，讲的是先让 AI 产品本身更容易评估，然后再尝试把所有 eval 固化下来。",
    },
    "2071637576318894515": {
        "translation": "这是一篇非常少见的深度文章，讲 Runway 的文化、技术和使命，或者说如何构建新的世界。",
    },
    "2071633874736804066": {
        "translation": "deepagents 里的 dynamic subagents！它允许你用程序方式启动子 Agent。我们重点展示了 6 种不同用例。",
    },
    "2071630837976822237": {
        "translation": "我们今天开始向早期合作伙伴推出 Trace Judge 模型。它被设计用来检测 agent 轨迹中的错误，成本约为闭源模型的 1/100。如果对早期访问感兴趣，可以在下面的表单注册。",
    },
}


def main() -> None:
    notes, categories = load_legacy_annotations()
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    raw_tweets = load_raw_tweets()
    account_payload = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    account_by_handle = {item["handle"].lower(): item for item in account_payload["accounts"]}

    all_rows = []
    for person in source["results"]:
        if not person["recent_count"]:
            continue
        for tweet in person["tweets"]:
            note = notes.get(tweet["id"])
            if not note:
                continue
            theme_id, signal, _, _ = note
            if signal != "high":
                continue
            details = SIGNAL_DETAILS[tweet["id"]]
            raw_tweet = raw_tweets.get(tweet["id"], {})
            created_at = datetime.fromisoformat(tweet["created_at"])
            all_rows.append(
                {
                    "id": tweet["id"],
                    "themeId": theme_id,
                    "expertHandle": person["handle"],
                    "createdAt": created_at.isoformat(),
                    "timeLabel": created_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M"),
                    "originalText": raw_tweet.get("text") or tweet["text"],
                    "translation": details["translation"],
                    "url": tweet["url"],
                    "media": normalize_media(raw_tweet.get("media", []), tweet["id"], "main"),
                    "quotedTweet": normalize_quoted_tweet(raw_tweet.get("quotedTweet"), tweet["id"]),
                }
            )

    all_rows.sort(key=lambda item: item["createdAt"], reverse=True)
    active_handles = {person["handle"].lower() for person in source["results"] if person["recent_count"]}
    expert_handles = sorted({row["expertHandle"].lower() for row in all_rows})
    experts = [build_expert(handle, account_by_handle) for handle in expert_handles]

    for expert in experts:
        cache_avatar(expert)

    theme_ids = [theme_id for theme_id in THEMES if any(row["themeId"] == theme_id for row in all_rows)]
    themes = [{"id": theme_id, **THEMES[theme_id]} for theme_id in theme_ids]

    start = datetime.fromisoformat(source["cutoff"]).astimezone(ZoneInfo("Asia/Shanghai"))
    end = datetime.fromisoformat(source["finishedAt"]).astimezone(ZoneInfo("Asia/Shanghai"))
    report = {
        "date": "2026-06-30",
        "title": "AI 专家动态日报",
        "headline": "近 24 小时高信号 X 原文，按主题归类展示；中文译文可切换查看。",
        "windowLabel": f"{start:%Y-%m-%d %H:%M} 至 {end:%Y-%m-%d %H:%M} 北京时间",
        "metrics": {
            "monitoredExperts": len(source["results"]),
            "activeExperts": len(active_handles),
            "selectedSignals": len(all_rows),
            "themes": len(themes),
        },
        "experts": experts,
        "themes": themes,
        "signals": all_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")


def load_raw_tweets() -> dict[str, dict]:
    tweets: dict[str, dict] = {}
    for path in RAW_SEARCH_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            tweet_id = str(item.get("id") or "")
            if tweet_id:
                tweets[tweet_id] = item
    return tweets


def normalize_quoted_tweet(raw: dict | None, parent_id: str) -> dict | None:
    if not raw:
        return None
    author = raw.get("author") or {}
    handle = author.get("username") or ""
    quoted_id = str(raw.get("id") or "")
    article = raw.get("article") or None
    quoted = {
        "id": quoted_id,
        "text": raw.get("text") or "",
        "authorName": author.get("name") or handle,
        "authorHandle": handle,
        "url": f"https://x.com/{handle}/status/{quoted_id}" if handle and quoted_id else "",
        "media": normalize_media(raw.get("media", []), parent_id, f"quoted-{quoted_id}"),
    }
    if article:
        quoted["article"] = {
            "title": article.get("title") or "",
            "previewText": article.get("previewText") or "",
        }
    return quoted


def normalize_media(items: list[dict], tweet_id: str, scope: str) -> list[dict]:
    media = []
    for index, item in enumerate(items or []):
        media_type = item.get("type")
        if media_type not in {"photo", "video"}:
            continue
        source_url = item.get("url") or item.get("previewUrl")
        if not source_url:
            continue
        local_url = cache_media(source_url, tweet_id, scope, index)
        media.append(
            {
                "type": media_type,
                "url": local_url,
                "width": item.get("width"),
                "height": item.get("height"),
                "videoUrl": item.get("videoUrl") or "",
                "durationMs": item.get("durationMs"),
            }
        )
    return media


def cache_media(url: str, tweet_id: str, scope: str, index: int) -> str:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    parsed_path = urlparse(url).path
    suffix = Path(parsed_path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = f"{tweet_id}-{scope}-{index}{suffix}"
    target = MEDIA_DIR / filename
    if target.exists() and target.stat().st_size > 1024:
        return f"./tweet-media/{filename}"
    result = subprocess.run(
        ["curl", "-L", "--fail", "--max-time", "20", "-o", str(target), url],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
        if target.exists():
            target.unlink()
        return url
    return f"./tweet-media/{filename}"


def load_legacy_annotations():
    spec = importlib.util.spec_from_file_location("legacy_visual_report", LEGACY_SCRIPT)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {LEGACY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NOTES, module.CATEGORIES


def build_expert(handle: str, account_by_handle: dict[str, dict]) -> dict:
    account = account_by_handle.get(handle.lower(), {})
    role = account.get("role") or ""
    org, title = split_role(role)
    tags = [tag for tag in account.get("tags", []) if not tag.startswith("P")]
    return {
        "handle": handle,
        "name": account.get("name") or handle,
        "avatar": f"./avatars/{handle}.jpg",
        "title": title,
        "org": org,
        "tags": tags[:2],
    }


def split_role(role: str) -> tuple[str, str]:
    if " / " in role:
        left, right = role.split(" / ", 1)
        return left.strip(), right.strip()
    if "；" in role:
        left, right = role.split("；", 1)
        return left.strip(), right.strip()
    return role.strip(), ""


def cache_avatar(expert: dict) -> None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    target = AVATAR_DIR / f"{expert['handle']}.jpg"
    if target.exists() and target.stat().st_size > 1024:
        return
    url = f"https://unavatar.io/twitter/{expert['handle']}"
    result = subprocess.run(
        ["curl", "-L", "--fail", "--max-time", "15", "-o", str(target), url],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
        if target.exists():
            target.unlink()
        svg_target = AVATAR_DIR / f"{expert['handle']}.svg"
        create_initial_avatar(expert, svg_target)
        expert["avatar"] = f"./avatars/{expert['handle']}.svg"


def create_initial_avatar(expert: dict, target: Path) -> None:
    initials = "".join(part[0] for part in expert["name"].split()[:2]).upper() or expert["handle"][:2].upper()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
<rect width="400" height="400" rx="92" fill="#111111"/>
<text x="200" y="224" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Arial,sans-serif" font-size="112" font-weight="700" fill="#ffffff">{html.escape(initials)}</text>
</svg>"""
    target.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
