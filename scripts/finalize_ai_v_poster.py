#!/usr/bin/env python3
"""Normalize a Browser poster capture into an exact RGB PNG, atomically."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
RGB_PNG_COLOR_TYPE = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Raw Browser capture outside the report directory")
    parser.add_argument("--output", type=Path, required=True, help="Final screenshots.png path")
    parser.add_argument("--width", type=int, default=1744)
    parser.add_argument("--height", type=int, default=960)
    return parser.parse_args()


def detect_image_format(data: bytes) -> str:
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data.startswith(JPEG_SIGNATURE):
        return "jpeg"
    raise RuntimeError("Browser capture is neither PNG nor JPEG")


def inspect_png(data: bytes) -> dict[str, Any]:
    if len(data) < 33 or not data.startswith(PNG_SIGNATURE):
        raise RuntimeError("normalized poster is not a complete PNG")
    if data[8:12] != struct.pack(">I", 13) or data[12:16] != b"IHDR":
        raise RuntimeError("normalized poster lacks a standard PNG IHDR")
    width, height = struct.unpack(">II", data[16:24])
    return {
        "width": width,
        "height": height,
        "bitDepth": data[24],
        "colorType": data[25],
    }


def validate_rgb_png(data: bytes, width: int, height: int) -> dict[str, Any]:
    info = inspect_png(data)
    if (info["width"], info["height"]) != (width, height):
        raise RuntimeError(
            f"poster dimensions are {info['width']}x{info['height']}, expected {width}x{height}"
        )
    if info["bitDepth"] != 8 or info["colorType"] != RGB_PNG_COLOR_TYPE:
        raise RuntimeError(
            "poster must be an 8-bit RGB PNG "
            f"(bitDepth={info['bitDepth']}, colorType={info['colorType']})"
        )
    return info


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary_output:
        temporary_output.write(data)
        temporary_output.flush()
        os.fsync(temporary_output.fileno())
        temporary_output_path = Path(temporary_output.name)
    temporary_output_path.replace(path)


def run_sips(source: Path, output: Path, image_format: str) -> None:
    completed = subprocess.run(
        ["/usr/bin/sips", "-s", "format", image_format, str(source), "--out", str(output)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0 or not output.exists():
        diagnostic = " ".join((completed.stderr or completed.stdout or "unknown sips failure").split())
        raise RuntimeError(f"sips could not create {image_format}: {diagnostic[-500:]}")


def normalize_capture(input_path: Path, output_path: Path, width: int, height: int) -> dict[str, Any]:
    source_data = input_path.read_bytes()
    source_format = detect_image_format(source_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ai-v-poster-") as directory:
        temporary_dir = Path(directory)
        normalized = temporary_dir / "normalized.png"
        if source_format == "jpeg":
            run_sips(input_path, normalized, "png")
        else:
            source_info = inspect_png(source_data)
            if source_info["colorType"] == RGB_PNG_COLOR_TYPE:
                shutil.copyfile(input_path, normalized)
            else:
                # A JPEG round-trip removes alpha/palette channels and makes
                # sips emit the RGB PNG required by the publication contract.
                intermediate = temporary_dir / "flattened.jpg"
                run_sips(input_path, intermediate, "jpeg")
                run_sips(intermediate, normalized, "png")

        normalized_data = normalized.read_bytes()
        info = validate_rgb_png(normalized_data, width, height)
        write_bytes_atomic(output_path, normalized_data)

    return {
        "sourceFormat": source_format,
        "output": str(output_path),
        **info,
    }


def main() -> int:
    args = parse_args()
    summary = normalize_capture(
        args.input.resolve(),
        args.output.resolve(),
        args.width,
        args.height,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
