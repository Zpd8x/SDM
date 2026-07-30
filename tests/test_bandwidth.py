from __future__ import annotations

import unittest

from sdm.bandwidth import BandwidthLimiter


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleep_calls: list[float] = []

    def clock(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.value += seconds


class BandwidthLimiterTests(unittest.TestCase):
    def test_limit_is_shared_across_sequential_chunks(self) -> None:
        fake = FakeTime()
        limiter = BandwidthLimiter(
            1024,
            clock=fake.clock,
            sleeper=fake.sleep,
        )

        limiter.throttle(1024)
        self.assertEqual(fake.value, 0.0)
        limiter.throttle(1024)

        self.assertAlmostEqual(fake.value, 1.0, places=6)
        self.assertGreater(len(fake.sleep_calls), 0)

    def test_unlimited_mode_never_sleeps(self) -> None:
        fake = FakeTime()
        limiter = BandwidthLimiter(
            0,
            clock=fake.clock,
            sleeper=fake.sleep,
        )
        limiter.throttle(10_000_000)
        self.assertEqual(fake.sleep_calls, [])

    def test_invalid_negative_limit_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BandwidthLimiter(-1)


if __name__ == "__main__":
    unittest.main()
