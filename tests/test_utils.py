from __future__ import annotations

import unittest

from sdm.utils import (
    format_bytes,
    format_eta,
    guess_filename,
    sanitize_filename,
    validate_download_url,
)


class UtilsTests(unittest.TestCase):
    def test_validate_download_url(self) -> None:
        self.assertEqual(validate_download_url("https://example.com/a.zip"), (True, ""))
        self.assertFalse(validate_download_url("ftp://example.com/a.zip")[0])
        self.assertFalse(validate_download_url("not-a-url")[0])

    def test_guess_and_sanitize_filename(self) -> None:
        self.assertEqual(
            guess_filename("https://example.com/My%20File.zip?token=1"),
            "My File.zip",
        )
        self.assertEqual(sanitize_filename('bad<>:"/\\|?*.zip'), "bad_________.zip")
        self.assertEqual(sanitize_filename("CON"), "_CON")

    def test_human_readable_formats(self) -> None:
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(5 * 1024 * 1024), "5.00 MB")
        self.assertEqual(format_eta(65), "01:05")
        self.assertEqual(format_eta(3661), "01:01:01")


if __name__ == "__main__":
    unittest.main()
