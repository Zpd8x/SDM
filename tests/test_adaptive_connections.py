from __future__ import annotations

import unittest

from sdm.adaptive_connections import (
    AdaptiveConnectionController,
    ServerConnectionProfile,
    initial_connection_count,
    lower_connection_count,
    raise_connection_count,
    server_key,
)


class AdaptiveConnectionTests(unittest.TestCase):
    def test_server_identity_ignores_path_and_default_port(self) -> None:
        self.assertEqual(
            server_key("https://Files.Example.com:443/a/b?token=short"),
            "https://files.example.com",
        )
        self.assertEqual(
            server_key("http://files.example.com:8080/file.bin"),
            "http://files.example.com:8080",
        )

    def test_saved_profile_caps_the_selected_limit(self) -> None:
        profile = ServerConnectionProfile(
            server_key="https://files.example.com",
            preferred_connections=2,
        )
        self.assertEqual(initial_connection_count(8, profile), 2)
        self.assertEqual(initial_connection_count(1, profile), 1)

    def test_connection_ladder_moves_one_safe_step(self) -> None:
        self.assertEqual(lower_connection_count(16), 8)
        self.assertEqual(lower_connection_count(1), 1)
        self.assertEqual(raise_connection_count(2, 8), 4)
        self.assertEqual(raise_connection_count(8, 8), 8)

    def test_rate_limit_reduces_once_then_recovers_cautiously(self) -> None:
        now = [0.0]
        events = []
        controller = AdaptiveConnectionController(
            requested=16,
            initial=8,
            on_change=events.append,
            clock=lambda: now[0],
            penalty_guard_seconds=2,
            recovery_cooldown_seconds=10,
        )

        first = controller.record_rate_limit(status_code=429, retry_after=4)
        duplicate = controller.record_rate_limit(
            status_code=429,
            retry_after=4,
        )
        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertEqual(controller.effective, 4)

        now[0] = 20
        for _ in range(8):
            controller.record_success()
        self.assertEqual(controller.effective, 8)
        self.assertEqual(
            [event.kind for event in events],
            ["rate_limit", "recovery"],
        )


if __name__ == "__main__":
    unittest.main()
