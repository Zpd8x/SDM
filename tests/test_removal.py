from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdm.models import DownloadRecord
from sdm.removal import (
    delete_download_artifacts,
    destination_is_shared,
    download_artifact_paths,
    segmented_parts_path,
)


class DownloadRemovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name)
        self.record = DownloadRecord(
            id="selected",
            url="https://example.com/file.bin",
            filename="file.bin",
            folder=str(self.folder),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_delete_artifacts_removes_final_partial_and_segments(self) -> None:
        self.record.final_path.write_bytes(b"final")
        self.record.temporary_path.write_bytes(b"partial")
        parts_path = segmented_parts_path(self.record)
        parts_path.mkdir()
        (parts_path / "segment_000.part").write_bytes(b"segment")

        deleted = delete_download_artifacts(self.record)

        self.assertEqual(
            set(deleted),
            set(download_artifact_paths(self.record)),
        )
        self.assertTrue(
            all(
                not path.exists()
                for path in download_artifact_paths(self.record)
            )
        )

    def test_missing_artifacts_are_safe(self) -> None:
        self.assertEqual(delete_download_artifacts(self.record), ())

    def test_shared_destination_is_detected_case_insensitively(self) -> None:
        other = DownloadRecord(
            id="other",
            url="https://example.com/other.bin",
            filename="FILE.BIN",
            folder=str(self.folder),
        )
        self.assertTrue(destination_is_shared(self.record, [self.record, other]))


if __name__ == "__main__":
    unittest.main()
