#!/usr/bin/env python3
"""Capture poster.html directly as a validated RGB PNG with headless Chrome."""

from __future__ import annotations

import argparse
import binascii
import json
import os
import re
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zlib
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
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Vanish accepts at most 256 KiB of media. Keep a little headroom for the
# transport rather than publishing an image that is only theoretically valid.
POSTER_TARGET_BYTES = 240 * 1024


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_delta = abs(estimate - left)
    above_delta = abs(estimate - above)
    upper_left_delta = abs(estimate - upper_left)
    if left_delta <= above_delta and left_delta <= upper_left_delta:
        return left
    if above_delta <= upper_left_delta:
        return above
    return upper_left


def decode_rgb_rows(png_data: bytes, width: int, height: int) -> tuple[bytes, list[bytearray]]:
    """Decode the exact RGB pixels from a non-interlaced 8-bit PNG."""
    if not png_data.startswith(PNG_SIGNATURE):
        raise RuntimeError("poster optimizer requires a PNG")
    position = len(PNG_SIGNATURE)
    ihdr: bytes | None = None
    idat: list[bytes] = []
    while position + 12 <= len(png_data):
        length = struct.unpack(">I", png_data[position : position + 4])[0]
        kind = png_data[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(png_data):
            raise RuntimeError("poster PNG has a truncated chunk")
        payload = png_data[position + 8 : position + 8 + length]
        if kind == b"IHDR":
            ihdr = payload
        elif kind == b"IDAT":
            idat.append(payload)
        elif kind == b"IEND":
            break
        position = end
    if ihdr is None or len(ihdr) != 13:
        raise RuntimeError("poster PNG is missing IHDR")
    png_width, png_height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if (png_width, png_height) != (width, height) or (bit_depth, color_type, compression, filter_method, interlace) != (
        8,
        2,
        0,
        0,
        0,
    ):
        raise RuntimeError("poster optimizer requires a non-interlaced 8-bit RGB PNG")
    stride = width * 3
    scanlines = zlib.decompress(b"".join(idat))
    if len(scanlines) != height * (stride + 1):
        raise RuntimeError("poster PNG scanline data is incomplete")
    rows: list[bytearray] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = scanlines[offset]
        filtered = scanlines[offset + 1 : offset + 1 + stride]
        current = bytearray(stride)
        for index, value in enumerate(filtered):
            left = current[index - 3] if index >= 3 else 0
            above = previous[index]
            upper_left = previous[index - 3] if index >= 3 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = paeth(left, above, upper_left)
            else:
                raise RuntimeError(f"poster PNG uses unsupported filter {filter_type}")
            current[index] = (value + predictor) & 0xFF
        rows.append(current)
        previous = current
        offset += stride + 1
    return ihdr, rows


def quantize_rows(rows: list[bytearray], bits: int) -> list[bytearray]:
    if bits == 8:
        return [bytearray(row) for row in rows]
    levels = (1 << bits) - 1
    return [
        bytearray(((value * levels + 127) // 255 * 255 + levels // 2) // levels for value in row)
        for row in rows
    ]


def filtered_scanlines(rows: list[bytearray]) -> bytes:
    """Use the lowest-cost PNG filter for every RGB scanline."""
    output = bytearray()
    previous = bytearray(len(rows[0]))
    for row in rows:
        candidates: list[tuple[int, int, bytearray]] = []
        for filter_type in range(5):
            filtered = bytearray(len(row))
            for index, value in enumerate(row):
                left = row[index - 3] if index >= 3 else 0
                above = previous[index]
                upper_left = previous[index - 3] if index >= 3 else 0
                if filter_type == 0:
                    predictor = 0
                elif filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = above
                elif filter_type == 3:
                    predictor = (left + above) // 2
                else:
                    predictor = paeth(left, above, upper_left)
                filtered[index] = (value - predictor) & 0xFF
            score = sum(min(value, 256 - value) for value in filtered)
            candidates.append((score, filter_type, filtered))
        _, filter_type, best = min(candidates, key=lambda candidate: candidate[0])
        output.append(filter_type)
        output.extend(best)
        previous = row
    return bytes(output)


def optimize_poster_png(png_data: bytes, width: int, height: int, max_bytes: int) -> tuple[bytes, int]:
    """Return the highest-fidelity RGB PNG that fits the media transport budget."""
    if len(png_data) <= max_bytes:
        return png_data, 8
    ihdr, rows = decode_rgb_rows(png_data, width, height)
    for bits in range(8, 1, -1):
        compressed = zlib.compress(filtered_scanlines(quantize_rows(rows, bits)), level=9)
        candidate = PNG_SIGNATURE + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", compressed) + png_chunk(b"IEND", b"")
        if len(candidate) <= max_bytes:
            validate_rgb_png(candidate, width, height)
            return candidate, bits
    raise RuntimeError(f"poster exceeds the {max_bytes} byte media budget after RGB optimization")


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
            source_bytes = len(png_data)
            png_data, quantization_bits = optimize_poster_png(
                png_data, width, height, POSTER_TARGET_BYTES
            )
            info = validate_rgb_png(png_data, width, height)
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
        "sourceBytes": source_bytes,
        "outputBytes": len(png_data),
        "maxBytes": POSTER_TARGET_BYTES,
        "quantizationBits": quantization_bits,
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
