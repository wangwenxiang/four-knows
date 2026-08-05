from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class BirdError(RuntimeError):
    pass


class BirdClient:
    def __init__(
        self,
        binary: str = "bird",
        timeout_seconds: int = 60,
        raw_dir: Path | None = None,
    ) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds
        self.raw_dir = raw_dir

    def user_tweets(
        self,
        handle: str,
        count: int = 30,
        max_pages: int = 1,
        delay_ms: int = 1000,
    ) -> Any:
        clean_handle = handle.lstrip("@")
        cmd = [
            self.binary,
            "--plain",
            "--no-color",
            "user-tweets",
            clean_handle,
            "-n",
            str(count),
            "--max-pages",
            str(max_pages),
            "--delay",
            str(delay_ms),
            "--json",
        ]
        return self._run(cmd, raw_name=f"{clean_handle}.json")

    def list_timeline(self, list_url: str, count: int = 100, max_pages: int = 1) -> Any:
        cmd = [
            self.binary,
            "--plain",
            "--no-color",
            "list-timeline",
            list_url,
            "-n",
            str(count),
            "--max-pages",
            str(max_pages),
            "--json",
        ]
        return self._run(cmd, raw_name="list-timeline.json")

    def _run(self, cmd: list[str], raw_name: str) -> Any:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if proc.returncode != 0:
            details = proc.stderr.strip() or proc.stdout.strip()
            raise BirdError(f"bird failed: {' '.join(cmd)}\n{details}")

        stdout = proc.stdout.strip()
        if not stdout:
            raise BirdError(f"bird returned no JSON: {' '.join(cmd)}")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise BirdError(f"bird returned non-JSON output: {stdout[:500]}") from exc

        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / raw_name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return payload
