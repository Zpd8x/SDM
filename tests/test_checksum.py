from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdm.checksum import (
    compute_sha256,
    is_valid_sha256,
    normalize_sha256,
)


class ChecksumTests(unittest.TestCase):
    def test_compute_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "hello.txt"
            path.write_bytes(b"hello world")
            self.assertEqual(
                compute_sha256(path, chunk_size=3),
                "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee"
                "9088f7ace2efcde9",
            )

    def test_validation_and_normalization(self) -> None:
        self.assertTrue(is_valid_sha256(""))
        self.assertTrue(is_valid_sha256("A" * 64))
        self.assertFalse(is_valid_sha256("g" * 64))
        self.assertFalse(is_valid_sha256("a" * 63))
        self.assertEqual(normalize_sha256("  ABC  "), "abc")


if __name__ == "__main__":
    unittest.main()
