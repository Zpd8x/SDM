import unittest
from sdm.media_inspector import build_format_selector, inspection_from_info


class MediaInspectorTests(unittest.TestCase):
    def test_inspection_parses_video_audio_hdr_and_subtitles(self):
        result = inspection_from_info("https://example.test/watch", {
            "title": "Demo", "extractor_key": "DemoSite", "duration": 120,
            "formats": [
                {"format_id": "137", "ext": "mp4", "width": 1920, "height": 1080, "fps": 60, "vcodec": "avc1", "acodec": "none", "tbr": 4500, "filesize": 1000, "protocol": "https", "dynamic_range": "HDR10"},
                {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "abr": 128, "filesize_approx": 500, "protocol": "https"},
            ],
            "subtitles": {"en": [{"ext": "vtt"}]},
            "automatic_captions": {"ar": [{"ext": "vtt"}, {"ext": "srt"}]},
        })
        self.assertEqual(result.title, "Demo")
        self.assertTrue(result.downloadable)
        self.assertEqual(result.formats[0].kind, "Video only")
        self.assertTrue(result.formats[0].hdr)
        self.assertEqual(result.formats[1].kind, "Audio only")
        self.assertEqual(len(result.subtitles), 2)

    def test_drm_media_is_not_downloadable(self):
        result = inspection_from_info("https://example.test/drm", {"title": "Protected", "is_drm": True, "formats": []})
        self.assertTrue(result.drm)
        self.assertFalse(result.downloadable)

    def test_playlist_and_live_flags(self):
        result = inspection_from_info("https://example.test/list", {"title": "List", "_type": "playlist", "entries": [{"id": "1"}, {"id": "2"}], "is_live": True, "formats": []})
        self.assertTrue(result.is_playlist)
        self.assertEqual(result.entries, 2)
        self.assertTrue(result.is_live)

    def test_format_selector_defaults(self):
        self.assertEqual(build_format_selector("137", "video"), "137")
        self.assertEqual(build_format_selector("", "audio"), "bestaudio/best")
        self.assertEqual(build_format_selector("", "video"), "bestvideo+bestaudio/best")


if __name__ == "__main__":
    unittest.main()
