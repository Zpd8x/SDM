from __future__ import annotations

import unittest
import urllib.error
from datetime import datetime, timezone
from email.message import Message

from sdm.retry_policy import is_rate_limited, retry_delay_seconds


class RetryPolicyTests(unittest.TestCase):
    @staticmethod
    def _http_error(code: int, retry_after: str = "") -> urllib.error.HTTPError:
        headers = Message()
        if retry_after:
            headers["Retry-After"] = retry_after
        return urllib.error.HTTPError(
            "https://example.test/file.bin",
            code,
            "test error",
            headers,
            None,
        )

    def test_429_uses_retry_after_seconds(self) -> None:
        error = self._http_error(429, "7")
        self.assertTrue(is_rate_limited(error))
        self.assertEqual(retry_delay_seconds(error, 0), 7.0)

    def test_503_is_also_treated_as_server_rate_limit(self) -> None:
        error = self._http_error(503, "3")
        self.assertTrue(is_rate_limited(error))
        self.assertEqual(retry_delay_seconds(error, 0), 3.0)

    def test_429_uses_retry_after_http_date(self) -> None:
        error = self._http_error(
            429,
            "Tue, 28 Jul 2026 14:00:12 GMT",
        )
        delay = retry_delay_seconds(
            error,
            0,
            now=datetime(2026, 7, 28, 14, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(delay, 12.0)

    def test_regular_error_keeps_short_exponential_backoff(self) -> None:
        self.assertFalse(is_rate_limited(TimeoutError()))
        self.assertEqual(retry_delay_seconds(TimeoutError(), 2), 4.0)


if __name__ == "__main__":
    unittest.main()
