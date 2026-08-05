# AI Expert Daily Report Handoff

## What this project contains

This project builds a static AI expert X/Twitter daily report from captured account data.

Current final report:

- `reports/ai-daily-2026-06-30/index.html`
- Desktop screenshot: `reports/screenshots/ai-daily-original-x-desktop.png`
- Mobile screenshot: `reports/screenshots/ai-daily-original-x-mobile.png`

## Main workflow

1. Generate React report data:

```bash
python3 scripts/build_report_app_data.py
```

2. Build the Vite/React app:

```bash
cd report-app
npm install
npm run build
cd ..
```

3. Inline CSS/JS into a single HTML file:

```bash
python3 scripts/bundle_report_app.py
```

## Important files

- `report-app/src/App.tsx`: report page structure.
- `report-app/src/components/ThemeSection.tsx`: category section and per-category Chinese translation toggle.
- `report-app/src/components/ExpertSignalCard.tsx`: X-style original post card, media, quoted tweet, article card.
- `report-app/src/styles/globals.css`: visual style.
- `report-app/src/types/report.ts`: TypeScript data schema.
- `scripts/build_report_app_data.py`: converts raw captured tweets into `report-app/src/data/daily-report.json`.
- `data/raw-search/2026-06-30/*.json`: source raw tweet data with media / quoted tweet fields.
- `reports/active-last-day-search-2026-06-30.json`: active-account search summary.

## Current design decisions

- The report prioritizes original X post content. Chinese translation is hidden by default.
- Translation is controlled per category, not globally.
- Original text is copied from `data/raw-search` raw `text` fields and preserves line breaks.
- Tweet media is cached into `report-app/public/tweet-media` and copied to the final report output.
- Quoted tweets and article preview fields are displayed when present in raw data.
- `node_modules` is intentionally not included in the handoff zip; run `npm install` inside `report-app`.
