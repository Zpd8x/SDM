from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from sdm.engine import DownloadControl
from sdm.models import DownloadRecord, DownloadStatus
from sdm.platform_media import PlatformMediaEngine


class _FakeYoutubeDL:
    last_options: dict[str, object] = {}

    def __init__(self, options: dict[str, object]) -> None:
        self.options = options
        type(self).last_options = options

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        return None

    def extract_info(self, _url: str, *, download: bool):
        assert download
        template = str(self.options["outtmpl"]["default"])
        output = Path(template.replace("%(ext)s", "mp4"))
        output.write_bytes(b"x" * 128)
        [hook] = self.options["progress_hooks"]
        hook(
            {
                "status": "downloading",
                "filename": str(output),
                "downloaded_bytes": 64,
                "total_bytes": 128,
                "speed": 32.0,
                "eta": 2,
            }
        )
        hook(
            {
                "status": "finished",
                "filename": str(output),
                "downloaded_bytes": 128,
                "total_bytes": 128,
                "speed": 0,
                "eta": 0,
            }
        )
        return {"requested_downloads": [{"filepath": str(output)}]}

    def prepare_filename(self, info) -> str:
        return str(info["requested_downloads"][0]["filepath"])


class PlatformMediaEngineTests(unittest.TestCase):
    def test_platform_download_reports_progress_and_real_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = DownloadRecord(
                id="media",
                url="https://www.youtube.com/watch?v=example",
                filename="Example video.mp4",
                folder=temporary_directory,
                status=DownloadStatus.DOWNLOADING,
                connections=8,
                media_kind="video",
            )
            progress: list[tuple[int, int, float, int | None]] = []
            metadata: list[int] = []
            modes: list[tuple[str, int]] = []
            fake_module = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
            with patch.dict(sys.modules, {"yt_dlp": fake_module}):
                result = PlatformMediaEngine().download(
                    record,
                    DownloadControl(),
                    on_progress=lambda *values: progress.append(values),
                    on_metadata=lambda total, _etag, _modified: metadata.append(
                        total
                    ),
                    on_mode=lambda mode, connections: modes.append(
                        (mode, connections)
                    ),
                )

            self.assertEqual(result.final_path.name, "Example video.mp4")
            self.assertEqual(result.total_bytes, 128)
            self.assertEqual(progress[-1], (128, 128, 0.0, 0))
            self.assertIn(128, metadata)
            self.assertEqual(modes, [("Platform media", 4)])
            self.assertIn(
                "best[acodec!=none][vcodec!=none]",
                str(_FakeYoutubeDL.last_options["format"]),
            )

    def test_audio_pages_select_an_audio_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = DownloadRecord(
                id="audio",
                url="https://soundcloud.com/artist/track",
                filename="Track.m4a",
                folder=temporary_directory,
                media_kind="audio",
            )
            fake_module = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
            with patch.dict(sys.modules, {"yt_dlp": fake_module}):
                PlatformMediaEngine().download(
                    record,
                    DownloadControl(),
                )
            self.assertEqual(
                _FakeYoutubeDL.last_options["format"],
                "bestaudio/best",
            )

    def test_platform_media_keeps_browser_referer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = DownloadRecord(
                id="referer",
                url="https://example.com/player",
                filename="Track.m4a",
                folder=temporary_directory,
                media_kind="audio",
                referer="https://example.com/album",
            )
            fake_module = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
            with patch.dict(sys.modules, {"yt_dlp": fake_module}):
                PlatformMediaEngine().download(
                    record,
                    DownloadControl(),
                )
            self.assertEqual(
                _FakeYoutubeDL.last_options["http_headers"]["Referer"],
                "https://example.com/album",
            )


if __name__ == "__main__":
    unittest.main()
