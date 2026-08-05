#!/usr/bin/env python3
"""Build a fixed-size AI V-Radar poster HTML from a dated posts.json."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CODEX_POSTER_COMMAND = [
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
LOW_SIGNAL_OPENERS = (
    "感谢", "谢谢", "恭喜", "很高兴", "自豪", "grateful", "thank", "thanks", "congrats", "excited",
)
TITLE_SIGNAL_TERMS = (
    "ai", "模型", "model", "agent", "智能体", "推理", "reasoning", "训练", "training", "基准", "benchmark",
    "生产", "production", "部署", "安全", "security", "漏洞", "vulnerab", "网络", "cyber", "机器人", "robot",
    "蛋白", "疾病", "drug", "protein", "意识", "consciousness", "开放权重", "open-weight",
)
POSTER_TITLE_LIMIT = 48
POSTER_SUBTITLE_LIMIT = 96


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Dated data/posts.json; defaults to latest")
    parser.add_argument("--selected-count", type=int, help="Poster精选 count; defaults to the actual selected-post count")
    parser.add_argument(
        "--no-codex",
        "--no-hermes",
        dest="no_codex",
        action="store_true",
        help="Use deterministic fallback copy",
    )
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


def translated_or_source(container: dict[str, Any], field: str) -> str:
    translated = container.get(field) if not container.get("translationFallback") else ""
    source_field = {
        "translationZh": "text",
        "titleZh": "title",
        "previewTextZh": "previewText",
    }.get(field, field.removesuffix("Zh"))
    return str(translated or container.get(source_field) or "").strip()


def primary_text(post: dict[str, Any]) -> str:
    return translated_or_source(post, "translationZh")


def quoted_text(post: dict[str, Any]) -> str:
    quote = post.get("quotedTweet")
    if isinstance(quote, dict):
        return translated_or_source(quote, "translationZh")
    return ""


def article_text(post: dict[str, Any]) -> str:
    article = post.get("article")
    if isinstance(article, dict):
        return "\n".join(
            part for part in (
                translated_or_source(article, "titleZh"),
                translated_or_source(article, "previewTextZh"),
            ) if part
        )
    return ""


def source_text(post: dict[str, Any]) -> str:
    parts = (primary_text(post), quoted_text(post), article_text(post))
    return "\n".join(part.strip() for part in parts if part.strip())


def clip(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ·—-：:")
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip("，,。.;；") + "…"


def clip_title(text: str, limit: int) -> str:
    """Prefer a natural clause boundary over an ellipsis in deterministic titles."""
    cleaned = re.sub(r"\s+", " ", text).strip(" ·—-：:")
    if len(cleaned) <= limit:
        return cleaned
    boundaries = [match.start() for match in re.finditer(r"[，,；;：:。！？!?]", cleaned)]
    usable = [position for position in boundaries if max(16, limit // 2) <= position <= limit]
    if usable:
        return cleaned[:max(usable)].rstrip("，,；;：:。！？!")
    return clip(cleaned, limit)


def fit_subtitle(text: str, limit: int = POSTER_SUBTITLE_LIMIT) -> str:
    """Use complete factual sentences that fit the fixed poster card.

    A poster is not the report: truncating a sentence with an ellipsis looks
    unfinished and wastes card space.  Prefer a complete short sentence; the
    full bilingual source remains in the report page.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    sentences = split_sentences(cleaned)
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*kept, sentence])
        if len(candidate) > limit:
            break
        kept.append(sentence)
    if kept:
        return " ".join(kept)
    if sentences:
        # A complete first sentence is more useful than an arbitrarily severed
        # clause. Normal production limits leave ample room for this case.
        return sentences[0]
    boundaries = [match.start() for match in re.finditer(r"[，,；;：:]", cleaned)]
    usable = [position for position in boundaries if max(24, limit // 2) <= position <= limit]
    if usable:
        return cleaned[:max(usable)].rstrip("，,；;：:") + "。"
    return cleaned[:limit].rstrip("，,；;：:。！？!? ") + "。"


def headline_font_size(title: str) -> int:
    """Fill a card's available line width without making dense titles unsafe."""
    units = 0.0
    for char in title:
        if "\u2e80" <= char <= "\u9fff" or "\uff00" <= char <= "\uffef":
            units += 1.0
        elif char.isspace():
            units += 0.25
        elif char.isupper() or char.isdigit():
            units += 0.68
        else:
            units += 0.58
    # About 1,430 px is available after the portrait and right inset.  The
    # bounds retain the dense-card floor while allowing short headlines to
    # occupy the otherwise empty right half of their card.
    return max(52, min(84, round(1430 / max(units, 1))))


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？!?])|\n+", text) if part.strip()]


def sentence_title_score(sentence: str, index: int) -> int:
    normalized = sentence.casefold().strip()
    score = min(14, len(normalized) // 12)
    score += 10 * sum(term.casefold() in normalized for term in TITLE_SIGNAL_TERMS)
    score += 5 * len(re.findall(r"\d+(?:\.\d+)?%?", normalized))
    if normalized.startswith(LOW_SIGNAL_OPENERS):
        score -= 20
    if any(opener in normalized for opener in LOW_SIGNAL_OPENERS):
        score -= 5
    return score - min(index, 4)


def primary_is_brief_endorsement(primary: str) -> bool:
    normalized = re.sub(r"https?://\S+", "", primary).strip()
    has_signal = any(term.casefold() in normalized.casefold() for term in TITLE_SIGNAL_TERMS)
    return len(normalized) < 48 and not has_signal


def compact_title_sentence(sentence: str) -> str:
    """Remove a small set of conversational wrappers without adding any facts."""
    cleaned = re.sub(r"\s+", " ", sentence).strip()
    comparison = re.match(
        r"^(?:我们)?(?:新的)?\s*(.+?模型)一个很好的特点是，\s*相比\s*(.+)$",
        cleaned,
    )
    if comparison:
        product = comparison.group(1)
        baseline, separator, outcome = comparison.group(2).partition("，")
        normalized_outcome = outcome.replace("它的 ", "").strip() if separator else ""
        if "token 效率高得多" in normalized_outcome:
            return f"{product.removesuffix('模型')}token 效率高于 {baseline.strip()}"
        return f"{product}相比 {comparison.group(2).replace('它的 ', '')}"
    return cleaned


def fallback_copy(post: dict[str, Any]) -> dict[str, str]:
    primary = primary_text(post)
    quoted = quoted_text(post)
    material = quoted if primary_is_brief_endorsement(primary) and quoted else primary
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])|\n+", material) if part.strip()]
    title_sentence = max(
        enumerate(sentences),
        key=lambda item: sentence_title_score(item[1], item[0]),
        default=(0, material),
    )
    title_index, title_material = title_sentence
    title = clip_title(compact_title_sentence(title_material or material), POSTER_TITLE_LIMIT)
    summary_sentences = [sentence for index, sentence in enumerate(sentences) if index != title_index]
    summary_source = " ".join(summary_sentences) or article_text(post) or quoted or primary
    return {"title": title, "summary": clip(summary_source, 54)}


def poster_subtitle(post: dict[str, Any], fallback: str) -> str:
    """Keep the quoted Chinese source intact; CSS manages the card viewport."""
    quoted = quoted_text(post)
    if quoted:
        return f"引用｜{quoted}"
    return fit_subtitle(fallback)


def author_key(post: dict[str, Any]) -> str:
    expert = post.get("expert") or {}
    author = post.get("author") or {}
    return str(expert.get("handle") or author.get("username") or post.get("id") or "unknown").casefold()


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
    raise ValueError("Codex did not return a JSON object")


def required_copy_keys(count: int) -> set[str]:
    return {
        f"p{index}_{field}"
        for index in range(1, count + 1)
        for field in ("title", "summary")
    }


def editorial_copy_with_metadata(
    posts: list[dict[str, Any]], use_codex: bool
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    fallback = [fallback_copy(post) for post in posts]
    if not posts:
        return fallback, {"copyBackend": "deterministic-fallback", "copyAttempts": 0, "copyRetries": 0, "copyError": "no stories"}
    if not use_codex:
        return [
            {
                "title": clip_title(item["title"], POSTER_TITLE_LIMIT),
                "summary": poster_subtitle(post, item["summary"]),
            }
            for post, item in zip(posts, fallback)
        ], {"copyBackend": "deterministic-fallback", "copyAttempts": 0, "copyRetries": 0, "copyError": "Codex disabled"}

    source = {
        f"p{index + 1}": {
            "primary": primary_text(post),
            "quoted": quoted_text(post),
            "article": article_text(post),
        }
        for index, post in enumerate(posts)
    }
    prompt = (
        "你是硅谷 AI 技术日报的海报编辑。基于 INPUT 的结构化原始材料，为每条生成准确、有信息量的中文标题和副标题。"
        "主标题只能概括 primary 主帖；不得把 quoted 引用帖或 article 的内容当作主标题。"
        "只有当 primary 是不含技术事实的简短转发/附和时，才可用 quoted 补足标题。"
        "标题 20-42 个汉字，突出具体技术进步、前沿或应用；副标题 36-64 个汉字，用第二层事实补充能力、数字、效果、约束或意义。"
        "材料较短时仍须覆盖其中全部关键事实，但不得同义反复来凑字数。"
        "不得编造，不写空泛宣传，不加引号或 Markdown。只返回扁平 JSON，例如 "
        '{"p1_title":"...","p1_summary":"..."}，每条都必须有 title 和 summary。\nINPUT:\n'
        + json.dumps(source, ensure_ascii=False)
    )
    expected_keys = required_copy_keys(len(posts))
    generated: dict[str, str] = {}
    errors: list[str] = []
    attempts = 0
    for attempt in range(1, 3):
        attempts = attempt
        try:
            completed = subprocess.run(
                CODEX_POSTER_COMMAND,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
        except subprocess.TimeoutExpired:
            errors.append("Codex timed out")
            continue
        except OSError:
            errors.append("Codex command unavailable")
            continue
        if completed.returncode != 0:
            errors.append(f"Codex exited with status {completed.returncode}")
            continue
        try:
            candidate = parse_flat_json(completed.stdout)
        except ValueError:
            errors.append("Codex returned no JSON object")
            continue
        missing = expected_keys - set(candidate)
        if missing:
            errors.append(f"Codex omitted {len(missing)} required copy fields")
            continue
        generated = candidate
        break

    metadata = {
        "copyBackend": "codex" if generated else "deterministic-fallback",
        "copyAttempts": attempts,
        "copyRetries": max(0, attempts - 1),
        "copyError": "" if generated else "; ".join(errors[-2:]),
    }
    result: list[dict[str, str]] = []
    for index, item in enumerate(fallback, start=1):
        generated_summary = generated.get(f"p{index}_summary") or item["summary"]
        result.append({
            "title": clip_title(generated.get(f"p{index}_title") or item["title"], POSTER_TITLE_LIMIT),
            "summary": poster_subtitle(posts[index - 1], generated_summary),
        })
    return result, metadata


def editorial_copy(posts: list[dict[str, Any]], use_codex: bool) -> list[dict[str, str]]:
    """Compatibility wrapper for callers that only need card copy."""
    return editorial_copy_with_metadata(posts, use_codex)[0]


def render_story(post: dict[str, Any], copy: dict[str, str], rank: int) -> str:
    expert = post.get("expert") or {}
    author = post.get("author") or {}
    name = expert.get("name") or author.get("name") or expert.get("handle") or "Unknown"
    handle = author.get("username") or expert.get("handle") or "unknown"
    role = expert.get("role") or expert.get("domain") or "AI"
    avatar = author.get("profileImageUrl") or ""
    category = post.get("topStoryCategory") if post.get("isTopStory") else "重要动态"
    avatar_html = f'<img src="{safe(avatar)}" alt="{safe(name)}">' if avatar else f'<span>{safe(str(name)[:1])}</span>'
    visible_length = len(copy["title"]) + len(copy["summary"])
    density_class = "story--sparse" if visible_length <= 82 else "story--dense" if visible_length >= 128 else "story--balanced"
    quote_class = " story--quote" if quoted_text(post) else ""
    title_size = headline_font_size(copy["title"])
    return f"""
      <article class="story {density_class}{quote_class}" style="--headline-size:{title_size}px">
        <div class="portrait"><div class="avatar">{avatar_html}</div><b>{rank}</b></div>
        <div class="story-body">
          <div class="byline"><strong>{safe(name)}</strong><em>{safe(category)}</em><span>@{safe(handle)} · {safe(role)}</span></div>
          <h2>{safe(copy['title'])}</h2>
          <p>{safe(copy['summary'])}</p>
        </div>
      </article>
    """.strip()


def select_poster_posts(all_posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    posts = all_posts[:3]
    if len(posts) != 3 or any(not post.get("isTopStory") or not post.get("topStoryEligible") for post in posts):
        raise RuntimeError("Poster requires exactly three eligible AI technical top stories")
    eligible_authors = {author_key(post) for post in all_posts if post.get("topStoryEligible")}
    required_author_count = min(3, len(eligible_authors))
    if len({author_key(post) for post in posts}) < required_author_count:
        raise RuntimeError("Poster top stories do not maximize author diversity")
    return posts


def main() -> int:
    args = parse_args()
    posts_path = (args.input or latest_posts_path()).resolve()
    input_bytes = posts_path.read_bytes()
    payload = json.loads(input_bytes)
    all_posts = [post for post in payload.get("posts", []) if isinstance(post, dict)]
    posts = select_poster_posts(all_posts)
    copies, copy_metadata = editorial_copy_with_metadata(posts, use_codex=not args.no_codex)
    generated = datetime.fromisoformat(str(payload["fetchStartedAt"]).replace("Z", "+00:00")).astimezone(SHANGHAI)
    window_hours = float(payload.get("windowHours") or 23)
    monitored = len(payload.get("experts") or [])
    selected_count = args.selected_count if args.selected_count is not None else len(all_posts)
    output_dir = posts_path.parents[1]
    poster_data = {
        "generatedAt": generated.isoformat(),
        "windowHours": window_hours,
        "monitored": monitored,
        "selected": selected_count,
        "inputSha256": hashlib.sha256(input_bytes).hexdigest(),
        **copy_metadata,
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
    write_text_atomic(
        output_dir / "data/poster.json",
        json.dumps(poster_data, ensure_ascii=False, indent=2),
    )
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
  .story{{display:grid;grid-template-columns:118px minmax(0,1fr);align-items:center;min-height:0;padding:14px 30px 14px 20px;border:2px solid #e0e2e7;border-radius:18px;background:rgba(255,255,255,.76)}}
  .portrait{{position:relative;display:grid;place-items:center}} .avatar{{display:grid;place-items:center;width:92px;height:92px;overflow:hidden;border:4px solid #151519;border-radius:50%;background:#111827;color:#fff;font-size:32px;font-weight:900}}
  .avatar img{{width:100%;height:100%;object-fit:cover;transform:scale(1.08)}} .portrait b{{position:absolute;right:0;bottom:-5px;display:grid;place-items:center;width:35px;height:35px;border:3px solid #151519;border-radius:50%;background:#fff;font-size:18px}}
  .story-body{{min-width:0}} .byline{{display:flex;align-items:center;gap:10px;min-width:0;margin-bottom:6px}} .byline strong{{font-size:29px;line-height:1;white-space:nowrap}} .byline em{{padding:7px 13px;border-radius:999px;background:#151519;color:#fff;font-size:17px;font-style:normal;font-weight:850;white-space:nowrap}} .byline span{{overflow:hidden;color:#666b74;font-size:18px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}}
  h2{{display:-webkit-box;max-height:2.12em;margin:0;overflow:hidden;overflow-wrap:anywhere;font-size:var(--headline-size,56px);line-height:1.06;font-weight:950;letter-spacing:-1.8px;-webkit-box-orient:vertical;-webkit-line-clamp:2}} .story p{{margin:8px 0 0;overflow-wrap:anywhere;color:#5d626b;font-size:30px;line-height:1.25;font-weight:750;white-space:normal}}
  .story--sparse p{{font-size:34px;line-height:1.22}} .story--dense p{{font-size:27px;line-height:1.23}}
  .story--quote p{{display:-webkit-box;max-height:3.75em;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:3}}
</style></head><body><div class="poster"><header><div><h1>硅谷 AI 原声 <span>| {generated.month}/{generated.day}</span></h1><div class="subtitle">全球核心专家动态精选 · 最近 {window_hours:g} 小时</div></div><div class="stats"><div class="stat"><strong>{monitored}</strong><small>人监控</small></div><div class="stat"><strong>{selected_count}</strong><small>条精选</small></div></div></header><main>{stories_html}</main></div></body></html>"""
    poster_path = output_dir / "poster.html"
    write_text_atomic(poster_path, page)
    print(json.dumps({"posterHtml": str(poster_path), "posterData": str(output_dir / "data/poster.json"), **poster_data}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
