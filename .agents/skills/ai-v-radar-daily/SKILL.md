---
name: ai-v-radar-daily
description: Generate, rebuild, inspect, validate, retain, and publish the local “硅谷 AI 原声” / AI V-Radar from X/Twitter with Bird and Codex. Use when Codex is asked to 抓取 Twitter/X AI 动态、生成最近 23 小时 AI 日报、更新或发布 AI V-Radar 页面、推送日报到 GitHub Pages、清理 7 天前历史日报、调整 AI 人物权重或前三条排序、补翻译或头像、检查每日自动任务，or work on `four-knows/ai-v-radar` and `scripts/fetch_ai_v_radar.py`.
---

# AI V-Radar Daily

Operate from the root of the `four-knows` repository that contains this skill. Treat the rules below as one contract; do not satisfy only the newest request.

## Run a fresh report

Run from the project root:

```bash
python3 scripts/fetch_ai_v_radar.py --hours 23 --fetch-mode search --search-batch-size 8 --search-max-pages 5 --workers 2 --retries 2 --avatar-workers 3 --translation-batch-size 8 --translation-workers 2 --translation-retries 2
```

Use the embedded watchlist in `ai_key_people_watchlist_visual.html` (currently 54 accounts). Use Bird only for read operations and the local non-interactive Codex CLI for Simplified Chinese translation.

Bird reads the saved X session directly from the local Chrome profile with `--cookie-source chrome`; it does not drive a live Chrome tab. Chrome may be closed during a run. Treat a logged-out X session, expired or cleared cookies, a different Chrome profile, or denied macOS cookie decryption as authentication failures and report them without exposing credentials.

Reserve `--reuse-data ai-v-radar/YYYYMMDD/data/posts.json` for repairing translation, avatar, layout, or ranking on an already fetched dataset. Never describe reuse as a new 23-hour fetch.

## Use local Codex for translation

- Translate primary posts, quoted posts, X Article titles, and X Article previews with the locally authenticated non-interactive `codex exec` CLI.
- Run translation in an ephemeral, read-only Codex session with approvals disabled. Keep the translation task isolated from unrelated project instructions.
- Preserve handles, URLs, hashtags, product names, model names, code, numbers, and technical claims.
- Cache translations by exact source text plus prompt version. A prompt-version change invalidates older cached translations so stale translation behavior does not silently persist.
- Require `translation.failed=0` and `translation.coverage=1.0`. Report failures instead of silently falling back to untranslated content.

## Enforce the time window

- Capture `fetchStartedAt` once, immediately when the fresh command starts.
- Set `windowStart = fetchStartedAt - 23 hours` exactly.
- Include a post only when `windowStart <= createdAtIso <= fetchStartedAt`.
- Do not use the command finish time, a calendar day, “since yesterday”, or a rolling boundary that moves during the fetch.
- Do not extend the window to fill the page or the first three positions.
- Store UTC source time in `createdAtIso`, store `createdAtBeijing` with `+08:00`, and display every card time in `Asia/Shanghai` with `北京` visible.
- Keep the exact Beijing window in `data/posts.json` and `data/run-report.json`, but do not repeat the full range in the visual header. Display the Beijing report date inline with the title.

## Select content

- Keep only content directly related to AI, models, agents, software, research, infrastructure, security, or technical industry developments.
- Evaluate the primary post together with quoted posts and X Article title/preview.
- Exclude low-signal replies unless media, a quote, or strong engagement makes them useful.
- Exclude recruitment completely, including hiring, open roles, job openings, applications, careers pages, “join our team”, “good role for you”, and Chinese 招聘/招人/岗位开放 language.
- Exclude lifestyle, generic company culture, swag, casual banter, and other nontechnical material unless the attached quote/article itself contains a substantive technical signal.
- When a lifestyle or swag wrapper quotes a technical post that is already selected directly, keep the substantive technical post once and remove the redundant wrapper.
- Deduplicate by post ID. Never backfill with old content when the current window is quiet.

## Guarantee the first three cards

Rank the first three independently from the remainder. Each must be a high-confidence example of at least one category:

1. AI 技术进步: a material model, system, performance, capability, efficiency, release, or benchmark improvement.
2. AI 技术前沿: frontier research, reasoning, training, alignment, interpretability, architecture, novel evaluation, or open-weight advances.
3. AI 技术应用: concrete deployment or use in coding, security, agents, robotics, workflows, infrastructure, or production systems.

Use technical evidence, author importance, engagement, quoted technical detail, and article substance. Favor current OpenAI authors first and current Anthropic/Claude authors second. Do not label commentary, policy chatter, marketing, vague hype, or recruitment as a top story merely because an important author posted it.

Mark the selected cards with `isTopStory=true`, `topStoryEligible=true`, `topStoryCategory`, and `topStoryScore`. A publishable poster requires exactly three genuinely eligible top stories that describe substantive AI technical progress, frontier research, or concrete technical application; never fill a poster position with commentary, marketing, policy chatter, or another non-eligible record. If fewer than three qualify, keep the generated local report artifacts but stop poster publication and report the shortage rather than weakening the rule or enlarging the window.

Maximize author diversity across the three top stories. Select the strongest eligible story from each distinct author before considering a second story from anyone. When at least three eligible authors exist, all three poster cards must come from different authors. When only one or two eligible authors exist, use the maximum available diversity and allow repetition only to fill the remaining positions; never publish three cards from one author when another eligible author is available.

After the first three, order by P0/P1 importance, current organization boost, and curated watchlist order. Apply `+10` signal weight to current OpenAI authors and `+9` to current Anthropic/Claude authors. Remove “前 OpenAI”, `former OpenAI`, and `ex-OpenAI` before detecting current OpenAI affiliation; a current Anthropic employee who previously worked at OpenAI remains Anthropic.

## Render the page

- Use the exact main title `硅谷 AI 原声` and place the report date inline in the same heading; do not render a separate date eyebrow or full-window subtitle.
- Show only the useful header metrics: monitored experts, active experts, and selected originals. Keep this row smaller than the title and minimize header padding so the content stream starts quickly.
- Render a dense, responsive two-column stream on desktop and one column on narrow screens.
- Show the complete English original first in the larger font. Show the complete Chinese translation after it in the smaller font. Never replace either with a summary.
- Preserve the same bilingual order in quoted posts and X Articles.
- Show a real X avatar for every primary author and every quoted author. Cache the URLs; do not invent avatar artwork when Bird can resolve the profile.
- Keep author name, handle, current role/domain, Beijing timestamp, engagement, media, quote, article, and direct X link.
- Do not add theme filters, priority filters, search, language switches, result counters, author shortcut navigation, author group headings, header topic metrics, or explanatory hero copy.

Write:

```text
ai-v-radar/YYYYMMDD/index.html
ai-v-radar/YYYYMMDD/data/posts.json
ai-v-radar/YYYYMMDD/data/run-report.json
ai-v-radar/translation-cache.json
ai-v-radar/avatar-cache.json
```

## Generate the daily poster

After the report passes content validation, run:

```bash
python3 scripts/render_ai_v_poster.py --input ai-v-radar/YYYYMMDD/data/posts.json --selected-count 13
```

This writes `poster.html` and `data/poster.json` in the dated report directory. Use exactly the first three display records after technical-importance ranking and author-diversity selection; all three must be eligible top stories. Generate concise Chinese technical titles and subtitles with the local non-interactive Codex CLI; preserve model/product names, numbers, and claims, and fall back to deterministic source-derived copy if Codex fails.

Render `poster.html` through local HTTP with the Browser skill. Set the viewport to 1744×960, take a full-page capture, and save the final RGB PNG as `ai-v-radar/YYYYMMDD/screenshots.png`. Do not rely on a viewport-only capture because browser chrome may reduce its width. If the Browser backend returns JPEG bytes, save a temporary `.jpg`, convert it to PNG with `sips -s format png`, then move the temporary source out of the report directory.

Match the established poster system:

- exact 1744×960 canvas;
- black-and-white editorial header `硅谷 AI 原声 | M/D`;
- subtitle for global expert highlights from the latest 23 hours;
- exact visible stats `54 人监控` and `13 条精选`;
- three large bordered cards with real author avatar, rank, author/role, category pill, large Chinese headline, and gray technical subtitle;
- no invented facts, decorative stock art, filters, navigation, or extra explanatory blocks.
- when a selected post quotes another post, use the quoted post's complete Chinese translation as the smaller two-line subtitle; only use the generated summary when there is no quoted post.

## Prune expired reports

Keep the repository bounded by retaining only the current Beijing report date and the previous six Beijing calendar dates. After a fresh report and poster are complete, but before final validation and publication, run:

```bash
python3 .agents/skills/ai-v-radar-daily/scripts/prune_old_reports.py --project . --keep-days 7 --reference-date YYYYMMDD
```

The reference date must be the fresh report's Beijing `YYYYMMDD`. The command deletes dated directories on or before `reference date - 7 days`, so exactly seven calendar dates remain when reports exist for every day. It may remove only direct, nonsymlink directories matching `ai-v-radar/YYYYMMDD`; preserve caches, undated files, invalid date names, and every path outside `ai-v-radar`.

Use the command's JSON `removed` list as the exact deletion set for Git staging and the final run summary. Do not run retention cleanup during a `--reuse-data`-only repair of an older report; cleanup belongs to a fresh production workflow so a historical layout or translation repair cannot unexpectedly remove reports.

## Protect the X session

- Never run `bird check` for this workflow.
- Never read, print, copy, save, or expose `auth_token`, `ct0`, cookies, local storage, or browser profile secrets.
- Use only Bird `search`, `user-tweets`, and other read-only profile/timeline operations needed for the report.
- Never run `tweet`, `reply`, `follow`, `unfollow`, or any other X write operation.
- Do not substitute unsourced web snippets or stale cached posts for a Bird fetch failure. Report the failed accounts.

## Validate before handoff

Run the bundled validator:

```bash
python3 .agents/skills/ai-v-radar-daily/scripts/validate_radar.py --project .
```

Require all of the following:

- exact 23-hour `windowStart`/`fetchStartedAt` interval;
- 54 requested accounts and zero failed accounts for a production run;
- unique IDs and every post inside the fixed window;
- UTC source timestamp, `+08:00` Beijing timestamp, and visible `北京` card time;
- zero technical-filter or recruitment violations in selected posts;
- exactly three eligible leading records and HTML cards marked as top stories for a publishable poster;
- maximum author diversity in the first three: three different authors whenever at least three eligible authors exist, otherwise no avoidable repetition;
- `translation.failed=0` and `translation.coverage=1.0`;
- primary and quoted avatar coverage both `1.0`, with `postsWithAvatar=postsSelected`;
- density-reducing UI shortcuts and removed controls remain absent.
- `screenshots.png` is a real 1744×960 PNG and `data/poster.json` contains `monitored=54`, `selected=13`, and exactly three displayed eligible stories.
- no dated report directory exists on or before the current report date minus seven days; only the latest seven Beijing calendar dates may remain.

Serve the repository through local HTTP for visual QA; do not validate only a `file://` page. Use the Browser skill when available, reload after rebuilding, verify the first three authors/content/times, and leave the final report tab as the deliverable.

## Publish the validated report to GitHub

Publishing is part of a successful production run. Do it only after the report and poster pass every validation requirement above.

- Publish only to the GitHub repository `git@github.com:wangwenxiang/four-knows.git` and branch `gh-pages`.
- Use the user's existing local GitHub SSH authentication for account `wangwenxiang`. Do not request, read, print, or store private keys or tokens.
- This is a GitHub repository, so no Jira task number is required. Use a concise conventional commit such as `chore: publish AI radar YYYYMMDD HHMM Beijing`.
- Confirm the current branch is `gh-pages`, then fetch the remote `gh-pages` branch over SSH before committing. If the remote is ahead or the histories have diverged, stop and report the condition; do not overwrite, force-push, or guess a merge.
- Stage only the current dated directory under `ai-v-radar/YYYYMMDD/`, `ai-v-radar/translation-cache.json`, `ai-v-radar/avatar-cache.json`, and the exact expired dated directories reported in the pruning command's `removed` list. Stage each removed tracked directory explicitly with `git add -u -- ai-v-radar/YYYYMMDD`; never broaden this to all of `ai-v-radar`. Include production script or skill files only when the current user request intentionally changed them. Never use `git add .`, and never include unrelated untracked files or temporary worktrees.
- Run `git diff --cached --check` and inspect the staged file list before committing. If no generated file changed, skip the commit and push and report that the remote is already current.
- Push explicitly over SSH with `git push git@github.com:wangwenxiang/four-knows.git HEAD:gh-pages`. Never force-push.
- After pushing, verify that `refs/heads/gh-pages` on the SSH remote equals local `HEAD`. If a push returns an unclear status, check the remote SHA before retrying so the same publication is not duplicated.

Report the absolute `index.html` and `screenshots.png` paths, exact Beijing window, selected count, active-author count, first-three authors/categories, recruitment and nontechnical drop counts, translation/avatar coverage, failed-account count, and the exact expired report directories removed by retention cleanup.
Also report the commit SHA and verified GitHub push status. If publication is blocked, keep the validated local artifacts and explain the exact Git state without force-pushing.
