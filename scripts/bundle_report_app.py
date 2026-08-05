from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/ai-daily-2026-06-30"
INDEX = REPORT_DIR / "index.html"


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")
    css_match = re.search(r'<link rel="stylesheet" crossorigin href="(?P<href>[^"]+)">', html)
    js_match = re.search(r'<script type="module" crossorigin src="(?P<src>[^"]+)"></script>', html)
    if not css_match or not js_match:
        raise SystemExit("Could not find Vite CSS/JS tags to inline")

    css_path = REPORT_DIR / css_match.group("href").lstrip("./")
    js_path = REPORT_DIR / js_match.group("src").lstrip("./")
    css = css_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")

    html = html.replace(css_match.group(0), f"<style>\n{css}\n</style>")
    html = html.replace(js_match.group(0), f"<script type=\"module\">\n{js}\n</script>")
    INDEX.write_text(html, encoding="utf-8")
    print(f"Inlined {css_path.relative_to(ROOT)} and {js_path.relative_to(ROOT)} into {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
