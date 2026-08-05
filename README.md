# AI V-Radar

Daily, read-only X/Twitter monitoring for the expert list embedded in
`ai_key_people_watchlist_visual.html`.

## Run

```bash
python3 scripts/fetch_ai_v_radar.py
```

## 热点发现范围

热点以最近 23 小时的 X 一手内容为主：固定 54 个账号负责稳定信号，人工筛选的 7 个账号作为独立扩展层保留。系统不再把 arXiv、出版物 RSS、实验室新闻 RSS 或普通 GitHub release 当作热点补充源；这些来源容易重复或偏离实际应用。

主要名单与规则：

- `config/ai_x_expansion_watchlist.json`：单独保留、上限固定为 7 人的 X 扩展名单；
- `reports/ai-hotspot-coverage-strategy.md`：应用导向的热点判断规则。

The command uses the local `bird` CLI with Chrome cookies, fixes an exact
24-hour window at the instant the command starts, searches the targets in small
batches, keeps technical posts inside that window, enriches each
active author with their real X avatar, translates English text to Chinese with
Hermes, and writes:

```text
ai-v-radar/YYYYMMDD/index.html
ai-v-radar/YYYYMMDD/data/posts.json
ai-v-radar/YYYYMMDD/data/run-report.json
ai-v-radar/translation-cache.json
ai-v-radar/avatar-cache.json
```

Useful options:

```bash
python3 scripts/fetch_ai_v_radar.py --limit 3
python3 scripts/fetch_ai_v_radar.py --hours 24 --search-batch-size 8 --workers 3
python3 scripts/fetch_ai_v_radar.py --fetch-mode timeline --count-per-user 20
python3 scripts/fetch_ai_v_radar.py --no-translate
python3 scripts/fetch_ai_v_radar.py --no-avatars
python3 scripts/fetch_ai_v_radar.py --reuse-data ai-v-radar/YYYYMMDD/data/posts.json
python3 scripts/render_ai_v_poster.py --input ai-v-radar/YYYYMMDD/data/posts.json --selected-count 13
```

Translations cover post text, quoted posts, and X Articles. The cache is shared
across dates, so repeated content is not translated again. If a batch is
incomplete, rerun with `--reuse-data`; only missing cache entries are sent to
Hermes.

The report orders authors by the watchlist's P0/P1 priority, gives current
OpenAI and Anthropic/Claude authors an additional strategic boost, and then
uses the curated watchlist order. Its first three cards are selected separately:
each must be a high-confidence AI technical advance, frontier result, or
technical application. The selector favors current OpenAI and Anthropic/Claude
authors and refuses to extend the 24-hour window to fill weak top stories.
English originals are shown first, followed by smaller Chinese translations.
Avatar URLs are obtained through Bird's read-only profile timeline response and
cached across dates. Posts without a direct AI/software/research/infrastructure
signal in their text, quoted post, or Article are dropped as `nonTechnical`.
Recruitment and job-opening posts are dropped separately as `recruitment`.
Every post carries an ISO `createdAtBeijing` value and displays its timestamp in
Beijing time.

The poster command creates `poster.html` and `data/poster.json` in the same
dated directory. Render `poster.html` at a 1744×960 viewport and save the
full-page capture as `screenshots.png`; the poster shows three leading stories
and the fixed editorial stats `54 人监控 / 13 条精选`.

For local browser QA, serve the repository over HTTP instead of opening the
report with a `file://` URL:

```bash
python3 -m http.server 8765
```

Then open `http://localhost:8765/ai-v-radar/YYYYMMDD/`.

The pipeline never calls Bird's write commands (`tweet`, `reply`, `follow`,
etc.). It only uses Bird's read-only `search` or `user-tweets` commands.
