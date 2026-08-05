#!/usr/bin/env python3
"""Run a one-off local-Codex editorial review for an AI V-Radar posts payload."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CODEX = [
    "codex", "-a", "never", "--sandbox", "read-only", "-C", "/private/tmp",
    "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "-",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def context(post: dict[str, Any]) -> dict[str, Any]:
    expert = post.get("expert") or {}
    author = post.get("author") or {}
    quote = post.get("quotedTweet") or {}
    article = post.get("article") or {}
    return {
        "id": str(post.get("id") or ""),
        "author": str(expert.get("handle") or author.get("username") or ""),
        "role": str(expert.get("role") or expert.get("domain") or ""),
        "engagement": {
            "likes": int(post.get("likeCount") or 0),
            "reposts": int(post.get("retweetCount") or 0),
            "replies": int(post.get("replyCount") or 0),
        },
        "primary": str(post.get("text") or ""),
        "quote": str(quote.get("text") or "") if isinstance(quote, dict) else "",
        "articleTitle": str(article.get("title") or "") if isinstance(article, dict) else "",
        "articlePreview": str(article.get("previewText") or "") if isinstance(article, dict) else "",
    }


def parse_json(output: str) -> dict[str, Any]:
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
            return value
    raise ValueError("Codex did not return a JSON object")


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    posts = [post for post in payload.get("posts", []) if isinstance(post, dict)]
    items = [context(post) for post in posts]
    prompt = """你是严格的硅谷 AI 技术日报主编。审读 INPUT 中每一条完整材料（primary、quote、article），不要按关键词凑数。

对每条返回：
- relevance：keep 或 drop。只有确实提供 AI/模型/agent/软件/研究/基础设施的新技术事实或有复用价值的工程经验才 keep；纯观点、泛泛讨论、营销、生活动态、招聘、单纯依赖版本观察均 drop。
- grade：A/B/C/D。A 是日报头条级；B 是值得保留但非头条；C/D 不保留。
- evidence：不超过 28 个汉字，说明材料中的具体技术事实；没有则写空字符串。
- rationale：不超过 36 个汉字，说明判断原因。
- topic：简短主题。
- category：仅当 A 时填写 AI 技术进步、AI 技术前沿或 AI 技术应用，否则空字符串。
- headlineEligible：仅 A 为 true。A 必须有可核实的新能力、研究结论、正式发布、量化结果，或明确的生产效果；作者身份和互动量不能替代证据。
- duplicateOf：若与 INPUT 中另一条是同一事件/同一观点的重复，填写其 id，否则空字符串。

然后给出 topStoryIds：最多 3 条 headlineEligible 的 id，按重要性排序，作者必须不同；不够三条就少于三条，绝不能补位。不要编造 INPUT 外的事实。
只输出合法 JSON：{"items":[...],"topStoryIds":[...]}
INPUT:
""" + json.dumps(items, ensure_ascii=False)
    completed = subprocess.run(CODEX, input=prompt, capture_output=True, text=True, timeout=360, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Codex failed")[-1200:])
    reviewed = parse_json(completed.stdout)
    reviewed["input"] = str(args.input.resolve())
    reviewed["candidateCount"] = len(items)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(reviewed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
