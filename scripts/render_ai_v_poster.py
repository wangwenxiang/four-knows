#!/usr/bin/env python3
"""Build a fixed-size AI V-Radar poster HTML from a dated posts.json."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Dated data/posts.json; defaults to latest")
    parser.add_argument("--selected-count", type=int, default=13, help="Poster精选 count")
    parser.add_argument("--no-hermes", action="store_true", help="Use deterministic fallback copy")
    return parser.parse_args()


def safe(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def latest_posts_path() -> Path:
    dated = sorted(
        path for path in (ROOT / "ai-v-radar").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{8}", path.name)
    )
    if not dated:
        raise RuntimeError("No dated AI V-Radar output found")
    return dated[-1] / "data/posts.json"


def source_text(post: dict[str, Any]) -> str:
    parts = [str(post.get("translationZh") or post.get("text") or "")]
    quote = post.get("quotedTweet")
    if isinstance(quote, dict):
        parts.append(str(quote.get("translationZh") or quote.get("text") or ""))
    article = post.get("article")
    if isinstance(article, dict):
        parts.extend((str(article.get("titleZh") or article.get("title") or ""), str(article.get("previewTextZh") or article.get("previewText") or "")))
    return "\n".join(part.strip() for part in parts if part.strip())


def clip(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ·—-：:")
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip("，,。.;；") + "…"


def fallback_copy(post: dict[str, Any]) -> dict[str, str]:
    primary = str(post.get("translationZh") or post.get("text") or "").strip()
    quote = post.get("quotedTweet") or {}
    quoted = str(quote.get("translationZh") or quote.get("text") or "").strip() if isinstance(quote, dict) else ""
    material = quoted if len(primary) < 24 and quoted else primary
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])|\n+", material) if part.strip()]
    title_parts: list[str] = []
    for sentence in sentences:
        title_parts.append(sentence)
        if len("".join(title_parts)) >= 24:
            break
    title = clip(" ".join(title_parts) or material, 42)
    summary_source = primary if material == quoted and primary else " ".join(sentences[len(title_parts) :]) or quoted or primary
    return {"title": title, "summary": clip(summary_source, 54)}


def parse_flat_json(output: str) -> dict[str, str]:
    cleaned = ANSI_ESCAPE.sub("", output).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return {str(key): str(text).strip() for key, text in value.items() if str(text).strip()}
    raise ValueError("Hermes did not return a JSON object")


def editorial_copy(posts: list[dict[str, Any]], use_hermes: bool) -> list[dict[str, str]]:
    fallback = [fallback_copy(post) for post in posts]
    if not use_hermes or not posts:
        return fallback
    source = {f"p{index + 1}": source_text(post) for index, post in enumerate(posts)}
    prompt = (
        "你是硅谷 AI 技术日报的海报编辑。基于 INPUT 的原始材料，为每条生成准确、有信息量的中文标题和副标题。"
        "标题 18-36 个汉字，突出具体技术进步、前沿或应用；副标题 18-42 个汉字，补充数字、效果或意义。"
        "不得编造，不写空泛宣传，不加引号或 Markdown。只返回扁平 JSON，例如 "
        '{"p1_title":"...","p1_summary":"..."}，每条都必须有 title 和 summary。\nINPUT:\n'
        + json.dumps(source, ensure_ascii=False)
    )
    try:
        completed = subprocess.run(
            ["hermes", "--ignore-rules", "-z", prompt],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        generated = parse_flat_json(completed.stdout) if completed.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        generated = {}
    result: list[dict[str, str]] = []
    for index, item in enumerate(fallback, start=1):
        result.append({
            "title": clip(generated.get(f"p{index}_title") or item["title"], 42),
            "summary": clip(generated.get(f"p{index}_summary") or item["summary"], 58),
        })
    return result


def render_story(post: dict[str, Any], copy: dict[str, str], rank: int) -> str:
    expert = post.get("expert") or {}
    author = post.get("author") or {}
    name = expert.get("name") or author.get("name") or expert.get("handle") or "Unknown"
    handle = author.get("username") or expert.get("handle") or "unknown"
    role = expert.get("role") or expert.get("domain") or "AI"
    avatar = author.get("profileImageUrl") or ""
    category = post.get("topStoryCategory") if post.get("isTopStory") else "重要动态"
    avatar_html = f'<img src="{safe(avatar)}" alt="{safe(name)}">' if avatar else f'<span>{safe(str(name)[:1])}</span>'
    return f"""
      <article class="story">
        <div class="portrait"><div class="avatar">{avatar_html}</div><b>{rank}</b></div>
        <div class="story-body">
          <div class="byline"><strong>{safe(name)}</strong><em>{safe(category)}</em><span>@{safe(handle)} · {safe(role)}</span></div>
          <h2>{safe(copy['title'])}</h2>
          <p>{safe(copy['summary'])}</p>
        </div>
      </article>
    """


def main() -> int:
    args = parse_args()
    posts_path = (args.input or latest_posts_path()).resolve()
    payload = json.loads(posts_path.read_text(encoding="utf-8"))
    posts = [post for post in payload.get("posts", []) if isinstance(post, dict)][:3]
    if not posts:
        raise RuntimeError(f"No posts found in {posts_path}")
    copies = editorial_copy(posts, use_hermes=not args.no_hermes)
    generated = datetime.fromisoformat(str(payload["fetchStartedAt"]).replace("Z", "+00:00")).astimezone(SHANGHAI)
    monitored = len(payload.get("experts") or [])
    output_dir = posts_path.parents[1]
    poster_data = {
        "generatedAt": generated.isoformat(),
        "monitored": monitored,
        "selected": args.selected_count,
        "stories": [
            {
                "id": post.get("id"),
                "author": (post.get("expert") or {}).get("name"),
                "category": post.get("topStoryCategory") if post.get("isTopStory") else "重要动态",
                **copy,
            }
            for post, copy in zip(posts, copies)
        ],
    }
    (output_dir / "data/poster.json").write_text(json.dumps(poster_data, ensure_ascii=False, indent=2), encoding="utf-8")
    stories_html = "".join(render_story(post, copy, index) for index, (post, copy) in enumerate(zip(posts, copies), start=1))
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=1744,initial-scale=1"><title>硅谷 AI 原声海报</title>
<style>
  *{{box-sizing:border-box}} html,body{{margin:0;width:1744px;height:960px;overflow:hidden;background:#f8f8fa;color:#121216;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
  .poster{{width:1744px;height:960px;padding:10px 20px 14px;border:1px solid #d8dae0;border-radius:22px;background:linear-gradient(145deg,#fff 0%,#f8f8fa 68%,#f2f5f8 100%)}}
  header{{height:90px;display:flex;align-items:flex-start;justify-content:space-between;border-bottom:4px solid #141418}}
  h1{{margin:0;font-size:58px;line-height:1;font-weight:950;letter-spacing:-2.8px}} h1 span{{font-weight:850}}
  .subtitle{{margin-top:1px;color:#5d616a;font-size:20px;font-weight:800;letter-spacing:.1px}}
  .stats{{display:flex;gap:8px}} .stat{{display:grid;place-items:center;min-width:96px;height:56px;padding:4px 12px;border:2px solid #151519;border-radius:15px;background:#fff;font-weight:900}}
  .stat:first-child{{background:#151519;color:#fff}} .stat strong{{font-size:28px;line-height:.8}} .stat small{{font-size:12px;line-height:1}}
  main{{height:842px;padding-top:10px;display:grid;grid-template-rows:repeat(3,1fr);gap:10px}}
  .story{{display:grid;grid-template-columns:98px minmax(0,1fr);align-items:center;min-height:0;padding:15px 26px 15px 18px;border:2px solid #e0e2e7;border-radius:18px;background:rgba(255,255,255,.76)}}
  .portrait{{position:relative;display:grid;place-items:center}} .avatar{{display:grid;place-items:center;width:76px;height:76px;overflow:hidden;border:4px solid #151519;border-radius:50%;background:#111827;color:#fff;font-size:28px;font-weight:900}}
  .avatar img{{width:100%;height:100%;object-fit:cover;transform:scale(1.08)}} .portrait b{{position:absolute;right:0;bottom:-3px;display:grid;place-items:center;width:31px;height:31px;border:3px solid #151519;border-radius:50%;background:#fff;font-size:16px}}
  .story-body{{min-width:0}} .byline{{display:flex;align-items:center;gap:9px;min-width:0;margin-bottom:5px}} .byline strong{{font-size:26px;line-height:1;white-space:nowrap}} .byline em{{padding:6px 12px;border-radius:999px;background:#151519;color:#fff;font-size:15px;font-style:normal;font-weight:850;white-space:nowrap}} .byline span{{overflow:hidden;color:#666b74;font-size:16px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}}
  h2{{margin:0;max-height:112px;overflow:hidden;font-size:51px;line-height:1.04;font-weight:950;letter-spacing:-2px}} .story p{{margin:7px 0 0;overflow:hidden;color:#5d626b;font-size:31px;line-height:1.1;font-weight:800;white-space:nowrap;text-overflow:ellipsis}}
</style></head><body><div class="poster"><header><div><h1>硅谷 AI 原声 <span>| {generated.month}/{generated.day}</span></h1><div class="subtitle">全球核心专家动态精选 · 最近 24 小时</div></div><div class="stats"><div class="stat"><strong>{monitored}</strong><small>人监控</small></div><div class="stat"><strong>{args.selected_count}</strong><small>条精选</small></div></div></header><main>{stories_html}</main></div></body></html>"""
    poster_path = output_dir / "poster.html"
    poster_path.write_text(page, encoding="utf-8")
    print(json.dumps({"posterHtml": str(poster_path), "posterData": str(output_dir / "data/poster.json"), **poster_data}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
