from __future__ import annotations

import json
import unittest
from pathlib import Path

from browser_host.install_host import (
    HOST_NAME,
    build_host_manifest,
    extension_id_from_key,
)


class BrowserExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extension_directory = (
            Path(__file__).resolve().parents[1] / "browser_extension"
        )
        cls.manifest = json.loads(
            (cls.extension_directory / "manifest.json").read_text(
                encoding="utf-8"
            )
        )

    def test_manifest_v3_and_version(self) -> None:
        self.assertEqual(self.manifest["manifest_version"], 3)
        self.assertEqual(self.manifest["version"], "2.0.0")
        self.assertEqual(
            self.manifest["background"]["service_worker"],
            "service_worker.js",
        )
        for icon_path in self.manifest["icons"].values():
            self.assertTrue((self.extension_directory / icon_path).is_file())

    def test_public_key_produces_expected_stable_extension_id(self) -> None:
        expected = (
            self.extension_directory / "extension_id.txt"
        ).read_text(encoding="utf-8").strip()
        self.assertEqual(
            extension_id_from_key(self.manifest["key"]),
            expected,
        )

    def test_manifest_has_required_network_capture_permissions(self) -> None:
        self.assertEqual(
            set(self.manifest["permissions"]),
            {
                "activeTab",
                "contextMenus",
                "downloads",
                "nativeMessaging",
                "storage",
                "webRequest",
            },
        )
        self.assertEqual(
            set(self.manifest["host_permissions"]),
            {"http://*/*", "https://*/*"},
        )
        self.assertEqual(
            set(self.manifest["optional_permissions"]),
            {"cookies"},
        )

    def test_native_host_manifest_restricts_the_allowed_origin(self) -> None:
        extension_id = extension_id_from_key(self.manifest["key"])
        manifest = build_host_manifest(
            Path("C:/SDM/SDMNativeHost.exe"),
            extension_id,
        )
        self.assertEqual(manifest["name"], HOST_NAME)
        self.assertEqual(
            manifest["allowed_origins"],
            [f"chrome-extension://{extension_id}/"],
        )

    def test_media_overlay_is_injected_into_http_pages(self) -> None:
        [content_script] = self.manifest["content_scripts"]
        self.assertEqual(
            set(content_script["matches"]),
            {"http://*/*", "https://*/*"},
        )
        self.assertTrue(content_script["all_frames"])
        for asset in (*content_script["js"], *content_script["css"]):
            self.assertTrue((self.extension_directory / asset).is_file())

    def test_media_overlay_handles_direct_and_platform_media(self) -> None:
        source = (
            self.extension_directory / "media_overlay.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"video, audio"', source)
        self.assertIn('"sdm-download-media"', source)
        self.assertIn("suggestedPageFilename", source)
        self.assertIn("mediaKindForPage", source)
        self.assertIn("instagram.com", source)
        self.assertIn("facebook.com", source)
        self.assertIn("soundcloud.com", source)
        self.assertIn("DRM is unsupported", source)
        self.assertIn('parsed.protocol === "http:"', source)
        self.assertIn('pathname.endsWith(".m3u8")', source)

    def test_context_menu_includes_the_page_itself(self) -> None:
        source = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        self.assertIn('const MENU_PAGE = "sdm-download-page"', source)
        self.assertIn('contexts: ["page", "frame"]', source)
        self.assertIn('title: "Download with SDM"', source)
        self.assertIn("media_kind", source)

    def test_browser_interception_waits_for_real_file_metadata(self) -> None:
        source = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        self.assertIn("waitForDownloadMetadata", source)
        self.assertIn("chrome.downloads.search", source)
        self.assertIn("total_bytes", source)
        self.assertIn("mime_type", source)
        self.assertIn("chrome.downloads.removeFile", source)

    def test_popup_can_disable_the_media_panel(self) -> None:
        popup_html = (
            self.extension_directory / "popup.html"
        ).read_text(encoding="utf-8")
        popup_js = (
            self.extension_directory / "popup.js"
        ).read_text(encoding="utf-8")
        self.assertIn('id="showMediaPanel"', popup_html)
        self.assertIn("showMediaPanel.checked", popup_js)

    def test_chatgpt_file_name_hint_is_sent_before_download(self) -> None:
        overlay = (
            self.extension_directory / "media_overlay.js"
        ).read_text(encoding="utf-8")
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"sdm-download-hint"', overlay)
        self.assertIn("filenameHintFromAnchor", overlay)
        self.assertIn("anchor.getAttribute(\"download\")", overlay)
        self.assertIn("recentDownloadHints", worker)
        self.assertIn("downloadHintKey", worker)
        self.assertIn("fileId?.startsWith(\"file_\")", worker)
        self.assertIn("chooseInterceptedFilename", worker)

    def test_hidden_and_page_audio_detection_contract(self) -> None:
        source = (
            self.extension_directory / "media_overlay.js"
        ).read_text(encoding="utf-8")
        self.assertIn("refreshAudioDetection", source)
        self.assertIn("declaredAudioUrl", source)
        self.assertIn("PerformanceObserver", source)
        self.assertIn("navigator.mediaSession?.metadata", source)
        self.assertIn("showAudioFallback", source)
        self.assertIn("bandcamp.com", source)
        self.assertIn("mixcloud.com", source)

    def test_smart_capture_uses_multiple_browser_signals(self) -> None:
        overlay = (
            self.extension_directory / "media_overlay.js"
        ).read_text(encoding="utf-8")
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        for signal in (
            "mediaCandidates",
            "collectStructuredMedia",
            "collectPerformanceCandidates",
            "rankedMediaCandidates",
            "capture_candidates",
            "capture_context",
        ):
            with self.subTest(signal=signal):
                self.assertIn(signal, overlay)
        self.assertIn("capture_candidates", worker)
        self.assertIn("page_url", worker)

    def test_network_capture_reads_media_response_metadata(self) -> None:
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        overlay = (
            self.extension_directory / "media_overlay.js"
        ).read_text(encoding="utf-8")
        self.assertIn("chrome.webRequest.onHeadersReceived", worker)
        self.assertIn('"content-type"', worker)
        self.assertIn('"content-disposition"', worker)
        self.assertIn('"sdm-get-network-media-candidates"', worker)
        self.assertIn('"application/vnd.apple.mpegurl"', worker)
        self.assertIn('source: "webrequest"', worker)
        self.assertIn('const allowed = new Set([', worker)
        self.assertNotIn('headers.get("set-cookie")', worker)
        self.assertIn("collectNetworkCandidates", overlay)
        self.assertIn("refreshNetworkDetection", overlay)

    def test_fragmented_stream_parts_are_not_direct_files(self) -> None:
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        self.assertIn("isFragmentedMediaResource", worker)
        self.assertIn("m4s|cmfa|cmfv", worker)
        self.assertIn("direct: !manifest && !fragmented", worker)

    def test_secure_session_bridge_is_explicit_and_site_scoped(self) -> None:
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        popup_html = (
            self.extension_directory / "popup.html"
        ).read_text(encoding="utf-8")
        popup_js = (
            self.extension_directory / "popup.js"
        ).read_text(encoding="utf-8")
        self.assertIn('id="useBrowserSession"', popup_html)
        self.assertIn("chrome.permissions.request", popup_js)
        self.assertIn("chrome.permissions.remove", popup_js)
        self.assertIn("chrome.cookies.getAll({ url }", worker)
        self.assertIn("source_urls: sourceUrls", worker)
        self.assertIn("cookies.length >= 128", worker)
        self.assertIn("useBrowserSession: false", worker)
        self.assertNotIn("console.log(cookie", worker)

    def test_site_adapter_source_and_final_urls_are_preserved(self) -> None:
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        self.assertIn("source_url: requestUrl", worker)
        self.assertIn("requestTrace?.final_url", worker)
        self.assertIn("payload.source_url", worker)
        self.assertIn("payload.final_url", worker)
        self.assertIn("response.adapter_label", (
            self.extension_directory / "popup.js"
        ).read_text(encoding="utf-8"))

    def test_redirect_trace_preserves_the_original_chatgpt_request(self) -> None:
        worker = (
            self.extension_directory / "service_worker.js"
        ).read_text(encoding="utf-8")
        overlay = (
            self.extension_directory / "media_overlay.js"
        ).read_text(encoding="utf-8")
        self.assertIn("recordRequestRedirect", worker)
        self.assertIn("recordDownloadResponse", worker)
        self.assertIn("takeDownloadTrace", worker)
        self.assertIn("request_url: requestUrl", worker)
        self.assertIn("payload.request_url", worker)
        self.assertIn("page_url: location.href", overlay)


if __name__ == "__main__":
    unittest.main()
