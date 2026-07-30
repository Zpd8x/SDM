from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdm.database import DownloadRepository
from sdm.smart_rules import (
    RuleContext,
    SmartRule,
    default_rules,
    evaluate_rules,
    load_rules,
    save_rules,
)


class SmartRulesTests(unittest.TestCase):
    def test_first_matching_rule_wins(self) -> None:
        rules = [
            SmartRule(
                id="first",
                name="First",
                domain="*.example.com",
                connections=2,
            ),
            SmartRule(
                id="second",
                name="Second",
                extension="zip",
                connections=8,
            ),
        ]
        decision = evaluate_rules(
            rules,
            RuleContext(
                url="https://cdn.example.com/archive.zip",
                filename="archive.zip",
            ),
        )
        self.assertTrue(decision.matched)
        self.assertEqual(decision.rule_id, "first")
        self.assertEqual(decision.connections, 2)

    def test_rule_can_choose_folder_category_and_start_mode(self) -> None:
        rule = SmartRule(
            id="audio",
            name="Audio",
            mime_prefix="audio/",
            target_folder="D:/Music",
            target_category="Music",
            connections=4,
            start_mode="later",
        )
        decision = evaluate_rules(
            [rule],
            RuleContext(
                url="https://media.example/stream",
                filename="track.mp3",
                mime_type="audio/mpeg",
            ),
        )
        self.assertEqual(decision.folder, "D:/Music")
        self.assertEqual(decision.category, "Music")
        self.assertEqual(decision.connections, 4)
        self.assertFalse(decision.start_immediately)

    def test_rules_persist_in_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = DownloadRepository(
                Path(temporary_directory) / "downloads.db"
            )
            custom = [
                SmartRule(
                    id="custom",
                    name="Custom",
                    extension="iso",
                    connections=8,
                )
            ]
            save_rules(repository, custom)
            loaded = load_rules(repository)
        self.assertEqual(loaded, custom)

    def test_all_rules_can_be_disabled_by_saving_an_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = DownloadRepository(
                Path(temporary_directory) / "downloads.db"
            )
            save_rules(repository, [])
            self.assertEqual(load_rules(repository), [])

    def test_defaults_protect_private_and_cloud_downloads(self) -> None:
        chatgpt = evaluate_rules(
            default_rules(),
            RuleContext(
                url=(
                    "https://chatgpt.com/backend-api/files/content"
                    "?id=file_123456"
                ),
                filename="project.zip",
            ),
        )
        drive = evaluate_rules(
            default_rules(),
            RuleContext(
                url="https://drive.google.com/file/d/abc/view",
                filename="project.zip",
            ),
        )
        self.assertEqual(chatgpt.connections, 2)
        self.assertEqual(drive.connections, 2)


if __name__ == "__main__":
    unittest.main()

class SmartRulesV120Tests(unittest.TestCase):
    def test_filename_glob_and_url_token_matching(self) -> None:
        rule = SmartRule(
            id="reports",
            name="Reports",
            filename_glob="report-*.pdf",
            url_contains="department=finance",
            target_category="Documents",
        )
        decision = evaluate_rules(
            [rule],
            RuleContext(
                url="https://example.test/export?department=finance",
                filename="report-july.pdf",
            ),
        )
        self.assertTrue(decision.matched)
        self.assertEqual(decision.category, "Documents")

    def test_rule_renames_file_and_builds_subfolder(self) -> None:
        rule = SmartRule(
            id="archive",
            name="Archive naming",
            extension="zip",
            target_folder="D:/Downloads",
            subfolder="Archives/2026",
            filename_prefix="SDM_",
            filename_suffix="_saved",
        )
        decision = evaluate_rules(
            [rule],
            RuleContext(
                url="https://example.test/package.zip",
                filename="package.zip",
            ),
        )
        self.assertEqual(decision.filename, "SDM_package_saved.zip")
        self.assertTrue(decision.folder.replace("\\", "/").endswith("Downloads/Archives/2026"))

    def test_unsafe_filename_fragments_are_sanitized(self) -> None:
        rule = SmartRule(
            id="safe",
            name="Safe",
            filename_prefix='bad<>:"/\\|?*',
            filename_suffix="_ok",
        )
        decision = evaluate_rules(
            [rule],
            RuleContext(url="https://example.test/a.bin", filename="a.bin"),
        )
        self.assertEqual(decision.filename, "bada_ok.bin")
