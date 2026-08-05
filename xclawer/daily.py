from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .bird import BirdClient, BirdError
from .config import load_accounts, load_config
from .normalize import dedupe_tweets, normalize_tweets
from .report import render_markdown, write_normalized_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AI experts X/Twitter daily report.")
    parser.add_argument("--accounts", default="config/accounts.json", help="JSON config with accounts.")
    parser.add_argument("--source", choices=("bird", "fixture"), default="bird")
    parser.add_argument("--fixture", help="Fixture JSON file for offline runs.")
    parser.add_argument("--list-url", help="X List URL or ID. When set, list timeline is fetched instead of per-account timelines.")
    parser.add_argument("--date", help="Report date, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--days", type=int, default=1, help="Keep tweets from the last N days.")
    parser.add_argument("--count-per-account", type=int, help="Tweets fetched per account.")
    parser.add_argument("--max-pages", type=int, help="Max bird pages per account/list.")
    parser.add_argument("--top", type=int, help="Top tweets to include.")
    parser.add_argument("--min-score", type=float, help="Minimum score included in report.")
    parser.add_argument("--out", help="Output markdown path.")
    args = parser.parse_args()

    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now().date()
    config = load_config(args.accounts if Path(args.accounts).exists() else None)
    bird_config: dict[str, Any] = config.get("bird", {})
    report_config: dict[str, Any] = config.get("report", {})

    count_per_account = args.count_per_account or int(bird_config.get("countPerAccount", 30))
    max_pages = args.max_pages or int(bird_config.get("maxPages", 1))
    delay_ms = int(bird_config.get("delayMs", 1000))
    timeout_seconds = int(bird_config.get("timeoutSeconds", 60))
    top_n = args.top or int(report_config.get("top", 25))
    min_score = args.min_score if args.min_score is not None else float(report_config.get("minScore", 0))

    raw_dir = Path("data/raw") / report_date.isoformat()
    if args.source == "fixture":
        tweets = load_fixture(args.fixture)
    else:
        tweets = fetch_with_bird(
            accounts_path=args.accounts,
            list_url=args.list_url,
            raw_dir=raw_dir,
            count_per_account=count_per_account,
            max_pages=max_pages,
            delay_ms=delay_ms,
            timeout_seconds=timeout_seconds,
        )

    tweets = filter_recent(dedupe_tweets(tweets), days=args.days)
    normalized_path = Path("data/normalized") / f"{report_date.isoformat()}.jsonl"
    write_normalized_jsonl(normalized_path, tweets)

    markdown = render_markdown(tweets, report_date=report_date, top_n=top_n, min_score=min_score)
    out_path = Path(args.out) if args.out else Path("reports") / f"ai-x-daily-{report_date.isoformat()}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Wrote {normalized_path}")
    print(f"Tweets: {len(tweets)}")
    return 0


def fetch_with_bird(
    accounts_path: str,
    list_url: str | None,
    raw_dir: Path,
    count_per_account: int,
    max_pages: int,
    delay_ms: int,
    timeout_seconds: int,
):
    client = BirdClient(timeout_seconds=timeout_seconds, raw_dir=raw_dir)
    if list_url:
        payload = client.list_timeline(list_url, count=count_per_account, max_pages=max_pages)
        return normalize_tweets(payload)

    accounts = load_accounts(accounts_path)
    if not accounts:
        raise SystemExit(f"No accounts found. Create {accounts_path} or pass --list-url.")

    all_tweets = []
    errors = []
    for account in accounts:
        try:
            payload = client.user_tweets(
                account.normalized_handle,
                count=count_per_account,
                max_pages=max_pages,
                delay_ms=delay_ms,
            )
        except BirdError as exc:
            errors.append(f"@{account.normalized_handle}: {exc}")
            continue
        all_tweets.extend(normalize_tweets(payload, default_author=account.normalized_handle))

    if errors:
        error_path = raw_dir / "_errors.txt"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text("\n\n".join(errors), encoding="utf-8")
    if not all_tweets and errors:
        raise SystemExit("bird failed for every account. See data/raw/*/_errors.txt")
    return all_tweets


def load_fixture(path: str | None):
    if not path:
        raise SystemExit("--fixture is required when --source fixture")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_tweets(payload)


def filter_recent(tweets, days: int):
    if days <= 0:
        return tweets
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [
        tweet
        for tweet in tweets
        if tweet.created_at is None or tweet.created_at.astimezone(timezone.utc) >= cutoff
    ]


if __name__ == "__main__":
    raise SystemExit(main())
