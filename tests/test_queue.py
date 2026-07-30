from __future__ import annotations

import unittest

from sdm.queue import DownloadQueue


class DownloadQueueTests(unittest.TestCase):
    def test_queue_promotes_in_fifo_order(self) -> None:
        queue = DownloadQueue(max_active=2)
        self.assertTrue(queue.request("one"))
        self.assertTrue(queue.request("two"))
        self.assertFalse(queue.request("three"))
        self.assertFalse(queue.request("four"))

        self.assertEqual(queue.pending_ids, ("three", "four"))
        self.assertEqual(queue.release("one"), ["three"])
        self.assertEqual(queue.active_ids, frozenset({"two", "three"}))
        self.assertEqual(queue.pending_ids, ("four",))

    def test_increasing_limit_promotes_waiting_download(self) -> None:
        queue = DownloadQueue(max_active=1)
        self.assertTrue(queue.request("one"))
        self.assertFalse(queue.request("two"))
        self.assertEqual(queue.set_max_active(2), ["two"])
        self.assertEqual(queue.active_ids, frozenset({"one", "two"}))

    def test_pending_request_is_not_duplicated(self) -> None:
        queue = DownloadQueue(max_active=1)
        queue.request("one")
        queue.request("two")
        queue.request("two")
        self.assertEqual(queue.pending_ids, ("two",))

    def test_busy_state_tracks_active_and_pending_downloads(self) -> None:
        queue = DownloadQueue(max_active=1)
        self.assertFalse(queue.is_busy)
        queue.request("one")
        queue.request("two")
        self.assertTrue(queue.is_busy)
        queue.release("one")
        self.assertTrue(queue.is_busy)
        queue.release("two")
        self.assertFalse(queue.is_busy)

    def test_pause_all_clears_active_and_pending_downloads(self) -> None:
        queue = DownloadQueue(max_active=1)
        queue.request("one")
        queue.request("two")
        queue.pause_all()
        self.assertEqual(queue.active_ids, frozenset())
        self.assertEqual(queue.pending_ids, ())
        self.assertFalse(queue.is_busy)

    def test_remove_pending_allows_deleting_a_queued_download(self) -> None:
        queue = DownloadQueue(max_active=1)
        queue.request("active")
        queue.request("delete-me")

        queue.remove_pending("delete-me")

        self.assertEqual(queue.pending_ids, ())
        self.assertEqual(queue.active_ids, frozenset({"active"}))


if __name__ == "__main__":
    unittest.main()
