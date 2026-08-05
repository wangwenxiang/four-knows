from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Account


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).expanduser().open("r", encoding="utf-8") as f:
        return json.load(f)


def load_accounts(path: str | Path | None) -> list[Account]:
    if path is None:
        return []
    config = load_json(path)
    accounts = []
    for item in config.get("accounts", []):
        if isinstance(item, str):
            accounts.append(Account(handle=item))
            continue
        accounts.append(
            Account(
                handle=str(item["handle"]),
                name=str(item.get("name", "")),
                tags=tuple(str(tag) for tag in item.get("tags", [])),
            )
        )
    return accounts


def load_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return load_json(path)
