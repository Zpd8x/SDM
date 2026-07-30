from __future__ import annotations

import unittest
from pathlib import Path


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[1]

    def test_capture_and_progress_windows_are_top_level(self) -> None:
        source = (
            self.project_root / "sdm" / "ui" / "main_window.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "BrowserCaptureDialog(self.repository, record, parent=None)",
            source,
        )
        self.assertIn("parent=None,", source)
        self.assertIn("schedule_window_activation(dialog)", source)
        self.assertIn("bring_window_to_front(dialog)", source)

    def test_windows_foreground_activation_and_taskbar_identity_exist(
        self,
    ) -> None:
        activation = (
            self.project_root / "sdm" / "ui" / "window_activation.py"
        ).read_text(encoding="utf-8")
        launcher = (self.project_root / "main.py").read_text(encoding="utf-8")
        self.assertIn("WindowStaysOnTopHint", activation)
        self.assertIn("SetForegroundWindow", activation)
        self.assertIn(
            "SetCurrentProcessExplicitAppUserModelID",
            launcher,
        )

    def test_completion_dialog_has_idm_style_actions(self) -> None:
        source = (
            self.project_root / "sdm" / "ui" / "completion_dialog.py"
        ).read_text(encoding="utf-8")
        for label in (
            '"Open"',
            '"Open with…"',
            '"Open folder"',
            '"Close"',
            '"Don\'t show this dialog again"',
        ):
            with self.subTest(label=label):
                self.assertIn(label, source)

    def test_progress_window_closes_before_completion_handoff(self) -> None:
        source = (
            self.project_root / "sdm" / "ui" / "download_progress_dialog.py"
        ).read_text(encoding="utf-8")
        completion_handler = source.split(
            "def _handle_completion(self)", 1
        )[1].split("def _mark_all_connections_completed", 1)[0]
        self.assertIn("self.hide()", completion_handler)
        self.assertIn("self.close()", completion_handler)

    def test_capture_url_starts_at_the_beginning(self) -> None:
        source = (
            self.project_root / "sdm" / "ui" / "browser_capture_dialog.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.url_edit.setCursorPosition(0)", source)

    def test_progress_dialog_explains_media_failures(self) -> None:
        source = (
            self.project_root / "sdm" / "ui" / "download_progress_dialog.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.error_value", source)
        self.assertIn("Why it failed:", source)

    def test_all_progress_bars_use_square_green_style(self) -> None:
        theme = (
            self.project_root / "sdm" / "ui" / "theme.py"
        ).read_text(encoding="utf-8")
        progress_style = theme.split("QProgressBar {", 1)[1].split(
            "QLineEdit", 1
        )[0]
        self.assertIn("QProgressBar::chunk", progress_style)
        self.assertIn("background-color: #22c55e;", progress_style)
        self.assertEqual(progress_style.count("border-radius: 0px;"), 2)
        self.assertNotIn("#3d83f7", progress_style)


if __name__ == "__main__":
    unittest.main()
