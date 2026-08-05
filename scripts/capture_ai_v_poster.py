#!/usr/bin/env python3
"""Capture poster.html directly as a validated RGB PNG with headless Chrome."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.finalize_ai_v_poster import detect_image_format, validate_rgb_png, write_bytes_atomic
from scripts.serve_ai_v_poster import create_server


CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--date", help="Report date YYYYMMDD; defaults to latest dated report")
    parser.add_argument("--output", type=Path, help="Defaults to ai-v-radar/YYYYMMDD/screenshots.png")
    parser.add_argument("--chrome", type=Path, help="Optional explicit Chrome/Chromium executable")
    parser.add_argument("--width", type=int, default=1744)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args()


def report_date(project: Path, requested: str | None) -> str:
    if requested:
        if not re.fullmatch(r"\d{8}", requested):
            raise RuntimeError("--date must use YYYYMMDD")
        return requested
    dated = sorted(
        path.name
        for path in (project / "ai-v-radar").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{8}", path.name)
    )
    if not dated:
        raise RuntimeError("No dated AI V-Radar report found")
    return dated[-1]


def find_chrome(explicit: Path | None = None) -> Path:
    candidates = (explicit,) if explicit is not None else CHROME_CANDIDATES
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("No supported Chrome/Chromium executable found")


def terminate_chrome_process_group(process: subprocess.Popen[Any]) -> None:
    """Stop only the isolated headless-Chrome process group created by this run."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def capture_poster(
    project: Path,
    date: str,
    output: Path,
    chrome: Path,
    width: int,
    height: int,
    timeout: int,
) -> dict[str, Any]:
    project = project.resolve()
    poster_html = project / "ai-v-radar" / date / "poster.html"
    if not poster_html.is_file():
        raise RuntimeError(f"Poster HTML does not exist: {poster_html}")

    server = create_server(project, "127.0.0.1", 0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/ai-v-radar/{date}/poster.html"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Local poster server returned HTTP {response.status}")

        with tempfile.TemporaryDirectory(prefix="ai-v-native-png-") as directory:
            temporary_dir = Path(directory)
            capture_path = temporary_dir / "capture.png"
            profile_path = temporary_dir / "chrome-profile"
            command = [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-crash-reporter",
                "--disable-breakpad",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--run-all-compositor-stages-before-draw",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                "--virtual-time-budget=5000",
                f"--user-data-dir={profile_path}",
                f"--screenshot={capture_path}",
                url,
            ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = time.monotonic() + max(10, timeout)
            png_data: bytes | None = None
            info: dict[str, Any] | None = None
            try:
                while time.monotonic() < deadline:
                    if capture_path.is_file():
                        candidate = capture_path.read_bytes()
                        try:
                            if detect_image_format(candidate) == "png":
                                candidate_info = validate_rgb_png(candidate, width, height)
                            else:
                                candidate_info = None
                        except RuntimeError:
                            candidate_info = None
                        if candidate_info is not None:
                            png_data = candidate
                            info = candidate_info
                            break
                    if process.poll() is not None and not capture_path.is_file():
                        raise RuntimeError(
                            f"Headless Chrome exited before writing PNG (status {process.returncode})"
                        )
                    time.sleep(0.1)
            finally:
                terminate_chrome_process_group(process)
            if png_data is None or info is None:
                raise RuntimeError(f"Headless Chrome did not produce a valid PNG within {timeout} seconds")
            write_bytes_atomic(output.resolve(), png_data)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    return {
        "backend": "headless-chrome-native-png",
        "chrome": str(chrome),
        "url": url,
        "output": str(output.resolve()),
        **info,
    }


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    date = report_date(project, args.date)
    output = args.output or (project / "ai-v-radar" / date / "screenshots.png")
    summary = capture_poster(
        project,
        date,
        output,
        find_chrome(args.chrome),
        args.width,
        args.height,
        args.timeout,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
