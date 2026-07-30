import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path

from sdm.database import DownloadRepository
from sdm.network_health import NetworkQuality, classify_network_error, classify_network_quality, probe_network
from sdm.recovery import choose_next_mirror, recovery_decision, validate_resume_metadata, wait_until_online


class _Conn:
    def close(self):
        pass


class NetworkRecoveryTests(unittest.TestCase):
    def test_quality_bands(self):
        self.assertEqual(classify_network_quality(False, None), NetworkQuality.OFFLINE)
        self.assertEqual(classify_network_quality(True, 40), NetworkQuality.EXCELLENT)
        self.assertEqual(classify_network_quality(True, 150), NetworkQuality.GOOD)
        self.assertEqual(classify_network_quality(True, 300), NetworkQuality.FAIR)
        self.assertEqual(classify_network_quality(True, 900), NetworkQuality.POOR)

    def test_probe_success_and_failure(self):
        self.assertTrue(probe_network(connector=lambda *a, **k: _Conn()).online)
        snap = probe_network(connector=lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
        self.assertFalse(snap.online)

    def test_error_classification(self):
        self.assertEqual(classify_network_error(socket.gaierror()), "dns_error")
        error = urllib.error.HTTPError("x", 429, "", {}, None)
        self.assertEqual(classify_network_error(error), "rate_limited")

    def test_recovery_backoff_and_terminal_errors(self):
        decision = recovery_decision(TimeoutError(), 2)
        self.assertTrue(decision.retry)
        self.assertEqual(decision.delay_seconds, 12.0)
        self.assertFalse(recovery_decision(OSError("SSL certificate failed"), 0).retry)

    def test_wait_until_online(self):
        states = iter([
            type("S", (), {"online": False})(),
            type("S", (), {"online": True})(),
        ])
        result = wait_until_online(probe=lambda: next(states), sleeper=lambda _: None, max_checks=2)
        self.assertTrue(result.online)

    def test_resume_validator(self):
        self.assertEqual(validate_resume_metadata(previous_etag="a", current_etag="b"), (False, "ETag changed"))
        self.assertTrue(validate_resume_metadata(previous_size=5, current_size=5)[0])

    def test_mirror_rotation(self):
        mirrors = ["https://a/file", "https://b/file"]
        self.assertEqual(choose_next_mirror(mirrors[0], mirrors), mirrors[1])

    def test_network_event_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = DownloadRepository(Path(temp) / "sdm.db")
            repo.record_network_event("abc", "offline", "Internet lost")
            events = repo.list_network_events("abc")
            self.assertEqual(events[0]["event_type"], "offline")


if __name__ == "__main__":
    unittest.main()
