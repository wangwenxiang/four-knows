from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Account:
    handle: str
    name: str = ""
    tags: tuple[str, ...] = ()

    @property
    def normalized_handle(self) -> str:
        return self.handle.lstrip("@").strip()


@dataclass
class Tweet:
    id: str
    author_handle: str
    text: str
    created_at: datetime | None = None
    url: str = ""
    author_name: str = ""
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    view_count: int = 0
    is_retweet: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def engagement(self) -> int:
        return self.like_count + self.retweet_count * 2 + self.reply_count + self.quote_count * 2
