from __future__ import annotations

import unittest

from sdm.models import DownloadRecord, DownloadStatus
from sdm.presentation import build_status_message, build_summary_text


def make_record(
    status: DownloadStatus,
    *,
    record_id: str = "test",
) -> DownloadRecord:
    return DownloadRecord(
        id=record_id,
        url="https://example.com/file.bin",
        filename="file.bin",
        folder="C:/Downloads",
        status=status,
    )


class PresentationTests(unittest.TestCase):
    def test_summary_includes_paused_downloads(self) -> None:
        records = [
            make_record(DownloadStatus.PAUSED, record_id="paused"),
            make_record(DownloadStatus.DOWNLOADING, record_id="active"),
            make_record(DownloadStatus.QUEUED, record_id="queued"),
            make_record(DownloadStatus.COMPLETED, record_id="completed"),
        ]
        self.assertEqual(
            build_summary_text(records),
            "4 total  •  1 active  •  1 queued  •  0 scheduled  •  "
            "1 paused  •  1 completed",
        )

    def test_status_messages_follow_download_state(self) -> None:
        self.assertEqual(
            build_status_message(make_record(DownloadStatus.PAUSED)),
            "Paused file.bin.",
        )
        self.assertEqual(
            build_status_message(make_record(DownloadStatus.COMPLETED)),
            "Completed file.bin.",
        )
        self.assertEqual(
            build_status_message(
                make_record(DownloadStatus.FAILED),
                detail="Network unavailable",
            ),
            "Failed file.bin. Error: Network unavailable",
        )

    def test_summary_and_message_include_stage_four_states(self) -> None:
        scheduled = make_record(
            DownloadStatus.SCHEDULED,
            record_id="scheduled",
        )
        scheduled.scheduled_at = "2030-01-02T03:04:00+00:00"
        verifying = make_record(
            DownloadStatus.VERIFYING,
            record_id="verifying",
        )

        summary = build_summary_text([scheduled, verifying])
        self.assertIn("1 active", summary)
        self.assertIn("1 scheduled", summary)
        self.assertIn("Scheduled file.bin for", build_status_message(scheduled))
        self.assertEqual(
            build_status_message(verifying),
            "Verifying SHA-256 for file.bin…",
        )


if __name__ == "__main__":
    unittest.main()
