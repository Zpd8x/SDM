from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sdm.schedule import (
    format_scheduled_local,
    normalize_scheduled_at,
    schedule_is_due,
)


class ScheduleTests(unittest.TestCase):
    def test_normalize_naive_and_utc_timestamps(self) -> None:
        self.assertEqual(
            normalize_scheduled_at("2030-01-02T03:04:05"),
            "2030-01-02T03:04:05+00:00",
        )
        self.assertEqual(
            normalize_scheduled_at("2030-01-02T04:04:05+01:00"),
            "2030-01-02T03:04:05+00:00",
        )

    def test_due_comparison(self) -> None:
        now = datetime(2030, 1, 2, 12, 0, tzinfo=timezone.utc)
        past = (now - timedelta(seconds=1)).isoformat()
        future = (now + timedelta(seconds=1)).isoformat()
        self.assertTrue(schedule_is_due(past, now=now))
        self.assertFalse(schedule_is_due(future, now=now))
        self.assertFalse(schedule_is_due("", now=now))

    def test_local_format_is_readable(self) -> None:
        value = format_scheduled_local("2030-01-02T03:04:00+00:00")
        self.assertRegex(value, r"^2030-01-02 \d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
