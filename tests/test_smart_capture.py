from __future__ import annotations

import unittest

from sdm.smart_capture import resolve_smart_capture


class SmartCaptureTests(unittest.TestCase):
    def test_high_confidence_dom_stream_replaces_platform_page(self) -> None:
        decision = resolve_smart_capture(
            {
                "url": "https://audiomack.com/artist/song/example",
                "page_url": "https://audiomack.com/artist/song/example",
                "media_kind": "audio",
                "capture_candidates": [
                    {
                        "url": "https://media.example.net/track.m4a?sig=1",
                        "kind": "audio",
                        "source": "dom",
                        "score": 980,
                        "direct": True,
                        "mime_type": "audio/mp4",
                    }
                ],
            }
        )
        self.assertEqual(
            decision.url,
            "https://media.example.net/track.m4a?sig=1",
        )
        self.assertEqual(decision.media_kind, "direct")
        self.assertEqual(decision.method, "smart-direct")
        self.assertEqual(
            decision.referer,
            "https://audiomack.com/artist/song/example",
        )
        self.assertEqual(decision.mime_type, "audio/mp4")

    def test_manifest_stays_with_platform_extractor(self) -> None:
        page_url = "https://example.com/watch/track"
        decision = resolve_smart_capture(
            {
                "url": page_url,
                "media_kind": "audio",
                "capture_candidates": [
                    {
                        "url": "https://cdn.example.com/master.m3u8",
                        "source": "performance",
                        "score": 900,
                        "direct": True,
                    }
                ],
            }
        )
        self.assertEqual(decision.url, page_url)
        self.assertEqual(decision.media_kind, "audio")
        self.assertEqual(decision.method, "platform-extractor")

    def test_untrusted_candidate_cannot_replace_url(self) -> None:
        page_url = "https://example.com/video"
        decision = resolve_smart_capture(
            {
                "url": page_url,
                "media_kind": "video",
                "capture_candidates": [
                    {
                        "url": "https://attacker.example/file.exe",
                        "source": "unknown",
                        "score": 1000,
                        "direct": True,
                    }
                ],
            }
        )
        self.assertEqual(decision.url, page_url)
        self.assertEqual(decision.media_kind, "video")

    def test_network_response_candidate_preserves_file_metadata(self) -> None:
        decision = resolve_smart_capture(
            {
                "url": "https://music.example/track",
                "page_url": "https://music.example/track",
                "media_kind": "audio",
                "capture_candidates": [
                    {
                        "url": "https://cdn.example/stream?id=42",
                        "source": "webrequest",
                        "score": 995,
                        "direct": True,
                        "mime_type": "audio/mp4",
                        "filename": "Artist - Track.m4a",
                        "total_bytes": 7340032,
                    }
                ],
            }
        )
        self.assertEqual(decision.method, "smart-direct")
        self.assertEqual(decision.filename, "Artist - Track.m4a")
        self.assertEqual(decision.total_bytes, 7340032)


if __name__ == "__main__":
    unittest.main()
