---
name: ai-v-radar-daily
description: Generate, rebuild, inspect, validate, retain, and publish the local “硅谷 AI 原声” / AI V-Radar from X/Twitter with Bird and Codex. Use when Codex is asked to 抓取 Twitter/X AI 动态、生成最近 23 小时 AI 日报、更新或发布 AI V-Radar 页面、推送日报到 GitHub Pages、清理 7 天前历史日报、调整 AI 人物权重或前三条排序、补翻译或头像、检查每日自动任务，or work on `four-knows/ai-v-radar` and `scripts/fetch_ai_v_radar.py`.
---

# AI V-Radar Daily

Operate from the root of the `four-knows` repository that contains this skill. Treat the rules below as one contract; do not satisfy only the newest request.

## Run a fresh report

Run from the project root:

```bash
python3 scripts/fetch_ai_v_radar.py --hours 23 --fetch-mode search --search-batch-size 8 --search-max-pages 5 --expansion-watchlist config/ai_x_expansion_watchlist.json --hotspot-queries config/ai_x_hotspot_queries.json --hotspot-max-pages 3 --workers 2 --retries 2 --editorial-ai --avatar-workers 3 --avatar-cache ai-v-radar/avatar-cache.json --translation-batch-size 8 --translation-workers 2 --translation-retries 2
```

Invoke every command that starts the local `codex` CLI, including the fresh fetch and poster-copy renderer, with the execution tool's `sandbox_permissions=require_escalated` from its first attempt. The nested CLI needs its normal authenticated local runtime. If that permission is unavailable, continue the report with the explicit translation or poster-copy fallback described below; do not block the whole daily publication solely because Codex is unavailable.

The semantic editorial stage is a hard quality gate and has no publication fallback: if the local Codex editorial backend is unavailable (for example a 401 API authentication failure), do not invent editorial decisions, do not render or publish anything, and do not lower the validation bar. The production script persists `ai-v-radar/YYYYMMDD/data/failed-run-report.json` with the acquisition statistics and a sanitized editorial error, then stops. Report that blocker and rerun the fresh production entry only after the credential issue is repaired; never describe a blocked run as a completed report.

Use the embedded 55-account core watchlist in `ai_key_people_watchlist_visual.html` plus the seven explicitly approved accounts in `config/ai_x_expansion_watchlist.json`, for 62 monitored accounts. Also execute all five X-only directions in `config/ai_x_hotspot_queries.json`; hotspot discoveries enrich the candidate pool but do not change the 62 monitored-account count. Re-check every hotspot result against that direction's configured `postMatchAny` terms across its primary post, quote, and article before it can enter the pool; retain matched-term provenance, merge multi-direction matches, and record per-direction selected/mismatch counts. Display the actual monitored count. Use Bird only for read operations and the local non-interactive Codex CLI for Simplified Chinese translation.

Bird uses the local Cookie Manager Chrome extension by default to retrieve a fresh `x.com` session at the start of each scan; it does not drive a live Chrome tab. The session is passed only through the Bird child process environment, never command-line arguments, generated files, logs, reports, or caches. `--cookie-source chrome` remains an explicit diagnostic fallback. Treat a disconnected extension, logged-out X session, expired or cleared cookies, or a different Chrome profile as authentication failures and report them without exposing credentials.

Reserve `--reuse-data ai-v-radar/YYYYMMDD/data/posts.json` for repairing translation, avatar, layout, or ranking on an already fetched dataset. Never describe reuse as a new 23-hour fetch.

## Use local Codex for translation

- Translate primary posts, quoted posts, X Article titles, and X Article previews with the locally authenticated non-interactive `codex exec` CLI.
- Run translation in an ephemeral, read-only Codex session with approvals disabled. Keep the translation task isolated from unrelated project instructions.
- Preserve handles, URLs, hashtags, product names, model names, code, numbers, and technical claims.
- Cache translations by exact source text plus prompt version. A prompt-version change invalidates older cached translations so stale translation behavior does not silently persist.
- Target `translation.failed=0` and `translation.coverage=1.0`. Immediately before the translation batches, the production script performs a real Codex preflight in the same execution environment. If the preflight or any later batch fails after retries, keep every successful/cache-hit translation, atomically update the shared cache, retain the complete English original, show `翻译暂不可用，请参阅上方英文原文。` at each unresolved location, and continue the daily publication. Record the exact failed count, coverage, fallback count, and compact sanitized diagnostic; never claim a fallback is a completed translation.

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
- Exclude recruitment completely, including hiring, open roles, job openings, applications, careers pages, role/application calls to action such as “Apply to be an …” or “Apply to join …”, “join our team”, “good role for you”, and Chinese 招聘/招人/岗位开放 language.
- Exclude lifestyle, generic company culture, swag, casual banter, and other nontechnical material unless the attached quote/article itself contains a substantive technical signal.
- Permanently exclude posts authored by Sam Altman (`@sama`) from selected content and top stories. Keep the account in the 62-person fetch count so acquisition coverage remains auditable.
- When a lifestyle or swag wrapper quotes a technical post that is already selected directly, keep the substantive technical post once and remove the redundant wrapper.
- Deduplicate by post ID, preserving every confirmed hotspot-direction tag when the same post appears in multiple searches. Never backfill with old content when the current window is quiet.
- After all eligibility, ranking, and top-story decisions, retain at most three selected posts per author. Keep the ranked first three and record any omitted later posts in `dropped.perAuthorCap`; do not relax this cap to fill the page.

## Guarantee the first three cards

Rank the first three independently from the remainder. Each must be a high-confidence example of at least one category:

1. AI 技术进步: a material model, system, performance, capability, efficiency, release, or benchmark improvement.
2. AI 技术前沿: frontier research, reasoning, training, alignment, interpretability, architecture, novel evaluation, or open-weight advances.
3. AI 技术应用: concrete deployment or use in coding, security, agents, robotics, workflows, infrastructure, or production systems.

Use technical evidence, author importance, engagement, quoted technical detail, and article substance. Favor current OpenAI authors first and current Anthropic/Claude authors second. Do not label commentary, policy chatter, marketing, vague hype, or recruitment as a top story merely because an important author posted it.

Mark the selected cards with `isTopStory=true`, `topStoryEligible=true`, `topStoryCategory`, and `topStoryScore`. A publishable poster requires exactly three genuinely eligible top stories that describe substantive AI technical progress, frontier research, or concrete technical application; never fill a poster position with commentary, marketing, policy chatter, or another non-eligible record. If fewer than three qualify, keep the generated local report artifacts but stop poster publication and report the shortage rather than weakening the rule or enlarging the window.

Maximize author diversity across the three top stories. Select the strongest eligible story from each distinct author before considering a second story from anyone. When at least three eligible authors exist, all three poster cards must come from different authors. When only one or two eligible authors exist, use the maximum available diversity and allow repetition only to fill the remaining positions; never publish three cards from one author when another eligible author is available. Do not fill two leading cards with different authors recounting the same underlying event; prefer the strongest original account and select the next distinct technical event.

After the first three, order by P0/P1 importance, current organization boost, and curated watchlist order. Apply `+10` signal weight to current OpenAI authors and `+9` to current Anthropic/Claude authors. Remove “前 OpenAI”, `former OpenAI`, and `ex-OpenAI` before detecting current OpenAI affiliation; a current Anthropic employee who previously worked at OpenAI remains Anthropic.

## Render the page

- Use the exact main title `硅谷 AI 原声` and place the report date inline in the same heading; do not render a separate date eyebrow or full-window subtitle.
- Show only the useful header metrics: monitored experts, active experts, and selected originals. Keep this row smaller than the title and minimize header padding so the content stream starts quickly.
- Render a dense, responsive two-column stream on desktop and one column on narrow screens.
- Show the complete English original first in the larger font. Show the complete Chinese translation after it in the smaller font. Never replace either with a summary.
- Preserve the same bilingual order in quoted posts and X Articles.
- Show a real X avatar for every primary author and every quoted author. Reuse the persistent `ai-v-radar/avatar-cache.json` first, persist avatars returned with post/search payloads, and query Bird only for genuinely new missing handles. On a 429 rate limit, stop scheduling more avatar lookups and leave publication blocked until a later retry can reach full coverage; do not repeatedly re-query cached authors.
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
python3 scripts/render_ai_v_poster.py --input ai-v-radar/YYYYMMDD/data/posts.json
```

This writes `poster.html` and `data/poster.json` in the dated report directory. Use exactly the first three display records after technical-importance ranking and author-diversity selection; all three must be eligible top stories. Generate concise Chinese technical titles and subtitles with the local non-interactive Codex CLI; the title must summarize the primary post, while a quote/article may only support it. Preserve model/product names, numbers, and claims, and fall back to deterministic source-derived copy if Codex fails. Persist the copy backend, retry count, and a sanitized error status in `data/poster.json`.

Capture the production poster directly as PNG with the isolated headless-Chrome helper:

```bash
python3 scripts/capture_ai_v_poster.py --project . --date YYYYMMDD
```

The helper starts its own collision-free local HTTP port, asks Chrome to write `capture.png` natively, requires exact 1744×960 8-bit RGB PNG bytes, and replaces `screenshots.png` atomically. It uses an isolated temporary Chrome profile and never reads the user's browser session. This native PNG path is the production default; do not create JPEG first.

Use the Browser skill afterward for visual QA when available. Only if the native helper is unavailable may a Browser capture be used as a recovery path: save the raw Browser bytes outside the report directory and run `scripts/finalize_ai_v_poster.py` to detect and normalize the actual format. JPEG-to-PNG conversion is an exception handler for a backend that returned JPEG, never the normal production sequence.

Match the established poster system:

- exact 1744×960 canvas;
- black-and-white editorial header `硅谷 AI 原声 | M/D`;
- subtitle for global expert highlights from the latest 23 hours;
- visible stats must use the actual monitored-account count and actual selected-post count;
- three large bordered cards with real author avatar, rank, author/role, category pill, large Chinese headline, and gray technical subtitle;
- no invented facts, decorative stock art, filters, navigation, or extra explanatory blocks.
- when a selected post quotes another post, pass the quoted post's complete Chinese translation through as the smaller subtitle. Do not shorten it in copy generation; the report page always retains the full bilingual quote.
- adapt typography to the actual headline width as well as content density: short single-line headlines may grow up to 84 px to use the right side of the card; balanced cards are about 56/30 px and dense cards are no smaller than 52/27 px. Do not leave a short headline as a small island with a large unused right-side gap.
- target a visually substantial text block in every card. Fix horizontal whitespace first through headline scale and line length, not by cutting source-derived quote text; never invent, repeat, or weaken content merely to fill the canvas.

## Prune expired reports

Keep the repository bounded by retaining only the current Beijing report date and the previous six Beijing calendar dates. After a fresh report and poster are complete, but before final validation and publication, run:

```bash
python3 .agents/skills/ai-v-radar-daily/scripts/prune_old_reports.py --project . --keep-days 7 --reference-date YYYYMMDD
```

The reference date must be the fresh report's Beijing `YYYYMMDD`. The command deletes dated directories on or before `reference date - 7 days`, so exactly seven calendar dates remain when reports exist for every day. It may remove only direct, nonsymlink directories matching `ai-v-radar/YYYYMMDD`; preserve caches, undated files, invalid date names, and every path outside `ai-v-radar`.

Use the command's JSON `removed` list as the exact deletion set for Git staging and the final run summary. Do not run retention cleanup during a `--reuse-data`-only repair of an older report; cleanup belongs to a fresh production workflow so a historical layout or translation repair cannot unexpectedly remove reports.

## Protect the X session

- Never run `bird check` for this workflow.
- Cookie Manager may read the live `x.com` session only when a read-only Bird scan begins. Keep the header and its `auth_token`/`ct0` components in process memory, pass them only in the Bird child environment, and discard them when the process exits.
- Never print, copy, save, expose, put on command lines, or write to logs/reports/caches `auth_token`, `ct0`, Cookie headers, local storage, or browser profile secrets.
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
- all configured core and expansion accounts (currently 62) requested, with zero failed accounts;
- all five configured X hotspot directions completed successfully;
- every retained hotspot post has configured matched-term evidence, correct multi-direction provenance, and auditable per-direction counts;
- unique IDs and every post inside the fixed window;
- UTC source timestamp, `+08:00` Beijing timestamp, and visible `北京` card time;
- zero technical-filter or recruitment violations in selected posts;
- exactly three eligible leading records and HTML cards marked as top stories for a publishable poster;
- maximum author diversity in the first three: three different authors whenever at least three eligible authors exist, otherwise no avoidable repetition;
- no two leading records recount the same underlying event;
- prefer translation `failed=0` and `coverage=1.0`; incomplete translation is a visible validation warning and does not block an otherwise valid publication;
- primary and quoted avatar coverage both `1.0`, with `postsWithAvatar=postsSelected`;
- density-reducing UI shortcuts and removed controls remain absent.
- `screenshots.png` is a real 1744×960 RGB PNG and `data/poster.json` contains the actual monitored/selected counts and exactly three displayed eligible stories.
- `data/poster.json.inputSha256` exactly matches the current `data/posts.json`; a poster built from stale input is a hard failure and must be regenerated before publication.
- each poster card uses the appropriate sparse/balanced/dense typography class, has no clipped byline, and does not leave a small text block floating in a mostly empty card.
- no dated report directory exists on or before the current report date minus seven days; only the latest seven Beijing calendar dates may remain.

Serve the repository through local HTTP for visual QA; do not validate only a `file://` page. Use the Browser skill when available, reload after rebuilding, verify the first three authors/content/times, and leave the final report tab as the deliverable.

## Recover quality failures and strengthen the system

Treat a failed production invariant as an ownership obligation, not merely a status to report. First check whether another daily job is active; never overlap a fetch. A single fresh rerun is appropriate for a transient acquisition, rendering, or publication failure. If the rerun reproduces the same content, ranking, validation, or publish defect, do not repeat the same fetch and do not publish a known-bad report.

Instead, preserve the evidence, identify the earliest layer that allowed the defect through, and repair that mechanism. Add a regression test using the actual failure phrasing or structure; add or strengthen an independent final validator guard when the defect concerns a publication invariant; then rebuild from the saved `posts.json` when the repair is limited to filtering, ranking, translation, avatar, or layout. Re-render the poster, recapture the native PNG, run the full validator, and visually inspect the changed first three cards before publication.

Only stop for external authority or state that cannot safely be changed here (for example unavailable X authentication, a remote Git divergence, or fewer than three genuinely eligible technical stories). In that case retain the local artifacts and report the precise blocker plus the next recovery action. Record the incident's invariant, root cause, guard added, test added, and verification result in the final handoff so later runs improve rather than merely repeat the failure.

An unavailable local Codex credential is also an external-state stop for the editorial stage: the production script persists the blocked-editorial evidence (`failed-run-report.json`) and the recovery action is to repair the credential and rerun the fresh production entry, not to reuse or weaken the editorial gate.

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
