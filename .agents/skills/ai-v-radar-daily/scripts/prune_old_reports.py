#!/usr/bin/env python3
"""Remove expired dated AI V-Radar directories with a strict retention boundary."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


DATE_DIR_RE = re.compile(r"\d{8}")
SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--reference-date", help="Beijing date in YYYYMMDD; defaults to today")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_date_dir(name: str) -> Optional[date]:
    if not DATE_DIR_RE.fullmatch(name):
        return None
    try:
        return datetime.strptime(name, "%Y%m%d").date()
    except ValueError:
        return None


def prune_report_dirs(
    output_root: Path,
    reference_date: date,
    keep_days: int = 7,
    dry_run: bool = False,
) -> dict[str, object]:
    if keep_days < 1:
        raise ValueError("keep_days must be at least 1")

    root = output_root.resolve()
    delete_on_or_before = reference_date - timedelta(days=keep_days)
    removed: list[str] = []
    skipped_symlinks: list[str] = []

    if root.exists():
        for child in sorted(root.iterdir(), key=lambda path: path.name):
            report_date = parse_date_dir(child.name)
            if report_date is None or report_date > delete_on_or_before:
                continue
            if child.is_symlink():
                skipped_symlinks.append(child.name)
                continue
            if not child.is_dir():
                continue
            resolved_child = child.resolve()
            if resolved_child.parent != root:
                raise RuntimeError(f"Refusing to remove path outside output root: {child}")
            if not dry_run:
                shutil.rmtree(resolved_child)
            removed.append(child.name)

    return {
        "keepDays": keep_days,
        "referenceDate": reference_date.strftime("%Y%m%d"),
        "deleteOnOrBefore": delete_on_or_before.strftime("%Y%m%d"),
        "removed": removed,
        "skippedSymlinks": skipped_symlinks,
        "dryRun": dry_run,
    }


def main() -> int:
    args = parse_args()
    reference_date = (
        datetime.strptime(args.reference_date, "%Y%m%d").date()
        if args.reference_date
        else datetime.now(SHANGHAI).date()
    )
    result = prune_report_dirs(
        args.project.resolve() / "ai-v-radar",
        reference_date=reference_date,
        keep_days=args.keep_days,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
