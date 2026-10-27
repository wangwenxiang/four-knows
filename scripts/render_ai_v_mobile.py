"""Render the approved mobile original-text layout from a real daily acquisition."""
import json
import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CHANNELS = {"research", "agent", "enterprise", "growth", "creative", "tools"}
TEMPLATE = Path(__file__).parent / "templates" / "ai_v_mobile.html"


def render_mobile(experts, posts, now, cutoff, translation=None):
    records = []
    for post in posts:
        channel = (post.get("editorial") or {}).get("channel")
        if channel not in CHANNELS:
            raise ValueError(f"Missing editorial channel for {post.get('id')}")
        records.append({
            "id": str(post["id"]), "track": channel, "source": post,
            "avatar": (post.get("author") or {}).get("profileImageUrl", ""),
        })
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    start = cutoff.astimezone(ZoneInfo("Asia/Shanghai"))
    data = {"records": records, "preview": False, "productionMonitored": len(experts)}
    notice = ""
    if translation and translation.get("failed"):
        notice = '<div class="notice">部分翻译暂不可用，相关位置保留原文并明确标注。</div>'
    replacements = {
        "__DATE__": local.strftime("%Y-%m-%d"),
        "__MONITORED__": str(len(experts)),
        "__ACTIVE__": str(len({p["expert"]["handle"].casefold() for p in posts})),
        "__SELECTED__": str(len(posts)),
        "__WINDOW__": f"{start:%Y-%m-%d %H:%M:%S} — {local:%Y-%m-%d %H:%M:%S}",
        "__NOTICE__": notice,
        "__CONTENT__": json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"),
    }
    rendered = TEMPLATE.read_text()
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    if data.get('layout') != 'mobile':
        raise SystemExit('Expected real mobile-acquisition posts.json')
    output = args.input.parent.parent / 'index.html'
    output.write_text(render_mobile(data['experts'], data['posts'],
        datetime.fromisoformat(data['fetchStartedAt']), datetime.fromisoformat(data['windowStart']), data.get('translation')))
    print(output)
