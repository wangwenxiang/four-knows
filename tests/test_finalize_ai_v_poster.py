from __future__ import annotations

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import capture_ai_v_poster as native_capture
from scripts import finalize_ai_v_poster as finalizer
from scripts import serve_ai_v_poster as poster_server


def png_header(width: int = 1744, height: int = 960, color_type: int = 2) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return finalizer.PNG_SIGNATURE + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\0\0\0\0"


class PosterFinalizerTests(unittest.TestCase):
    def test_rgb_png_is_published_atomically(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "capture.raw"
            output = root / "report/screenshots.png"
            raw.write_bytes(png_header())

            result = finalizer.normalize_capture(raw, output, 1744, 960)

            self.assertEqual(result["sourceFormat"], "png")
            self.assertEqual(result["colorType"], 2)
            self.assertEqual(output.read_bytes(), png_header())
            self.assertEqual(list(output.parent.glob(".screenshots.png.*")), [])

    def test_jpeg_bytes_are_converted_even_with_a_raw_extension(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "capture.raw"
            output = root / "screenshots.png"
            raw.write_bytes(b"\xff\xd8\xff browser-jpeg")

            def fake_sips(_source: Path, destination: Path, image_format: str) -> None:
                self.assertEqual(image_format, "png")
                destination.write_bytes(png_header())

            with patch.object(finalizer, "run_sips", side_effect=fake_sips) as run_sips:
                result = finalizer.normalize_capture(raw, output, 1744, 960)

            self.assertEqual(result["sourceFormat"], "jpeg")
            self.assertTrue(output.read_bytes().startswith(finalizer.PNG_SIGNATURE))
            run_sips.assert_called_once()

    def test_wrong_dimensions_do_not_replace_an_existing_poster(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "capture.raw"
            output = root / "screenshots.png"
            raw.write_bytes(png_header(width=1600))
            output.write_bytes(b"previous-good-poster")

            with self.assertRaisesRegex(RuntimeError, "expected 1744x960"):
                finalizer.normalize_capture(raw, output, 1744, 960)

            self.assertEqual(output.read_bytes(), b"previous-good-poster")

    def test_non_rgb_png_is_flattened_before_publication(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "capture.raw"
            output = root / "screenshots.png"
            raw.write_bytes(png_header(color_type=6))

            def fake_sips(_source: Path, destination: Path, image_format: str) -> None:
                destination.write_bytes(
                    b"\xff\xd8\xff flattened" if image_format == "jpeg" else png_header()
                )

            with patch.object(finalizer, "run_sips", side_effect=fake_sips) as run_sips:
                result = finalizer.normalize_capture(raw, output, 1744, 960)

            self.assertEqual(run_sips.call_count, 2)
            self.assertEqual(result["colorType"], 2)


class PosterServerTests(unittest.TestCase):
    def test_port_zero_allocates_a_free_local_port(self) -> None:
        with TemporaryDirectory() as directory:
            server = poster_server.create_server(Path(directory), "127.0.0.1", 0)
            try:
                self.assertGreater(server.server_address[1], 0)
            finally:
                server.server_close()


class NativePosterCaptureTests(unittest.TestCase):
    def test_headless_chrome_is_requested_to_write_native_png(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "ai-v-radar/20260724"
            report.mkdir(parents=True)
            (report / "poster.html").write_text("<html><body>poster</body></html>", encoding="utf-8")
            output = report / "screenshots.png"
            chrome = root / "chrome"
            chrome.write_text("", encoding="utf-8")

            class FakeProcess:
                pid = 999999
                returncode = 0

                def poll(self):
                    return 0

            def fake_popen(command: list[str], **_kwargs: object):
                screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
                Path(screenshot_arg.removeprefix("--screenshot=")).write_bytes(png_header())
                return FakeProcess()

            with (
                patch.object(native_capture.subprocess, "Popen", side_effect=fake_popen) as popen,
                patch.object(native_capture, "terminate_chrome_process_group"),
            ):
                    result = native_capture.capture_poster(
                        root,
                        "20260724",
                        output,
                        chrome,
                        1744,
                        960,
                        60,
                    )

            command = popen.call_args.args[0]
            self.assertTrue(any(item.endswith("capture.png") for item in command if item.startswith("--screenshot=")))
            self.assertEqual(result["backend"], "headless-chrome-native-png")
            self.assertEqual(result["colorType"], 2)
            self.assertEqual(output.read_bytes(), png_header())


if __name__ == "__main__":
    unittest.main()
