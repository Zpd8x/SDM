from __future__ import annotations

import unittest

from sdm.categories import (
    categorize_filename,
    category_folder_setting_key,
    normalize_category,
)


class DownloadCategoryTests(unittest.TestCase):
    def test_common_extensions_are_categorized(self) -> None:
        cases = {
            "manual.PDF": "Documents",
            "movie.mkv": "Videos",
            "song.flac": "Music",
            "photo.webp": "Images",
            "bundle.tar": "Archives",
            "installer.msi": "Programs",
            "data.bin": "Other",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(categorize_filename(filename), expected)

    def test_auto_and_manual_category_are_normalized(self) -> None:
        self.assertEqual(normalize_category("Auto", "book.epub"), "Documents")
        self.assertEqual(normalize_category("videos", "file.bin"), "Videos")
        self.assertEqual(normalize_category("Unknown", "file.mp3"), "Other")

    def test_category_folder_setting_key_is_stable(self) -> None:
        self.assertEqual(
            category_folder_setting_key("Documents"),
            "category_folder_documents",
        )
        self.assertEqual(
            category_folder_setting_key("unknown"),
            "category_folder_other",
        )


if __name__ == "__main__":
    unittest.main()
