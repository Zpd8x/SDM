from __future__ import annotations

from collections import deque


class DownloadQueue:
    """Small deterministic queue that limits active download records."""

    def __init__(self, max_active: int = 2) -> None:
        self._max_active = max(1, int(max_active))
        self._active: set[str] = set()
        self._pending: deque[str] = deque()

    @property
    def max_active(self) -> int:
        return self._max_active

    @property
    def active_ids(self) -> frozenset[str]:
        return frozenset(self._active)

    @property
    def pending_ids(self) -> tuple[str, ...]:
        return tuple(self._pending)

    @property
    def is_busy(self) -> bool:
        return bool(self._active or self._pending)

    def request(self, record_id: str) -> bool:
        """Return True when the record may start immediately."""
        if record_id in self._active:
            return True
        if len(self._active) < self._max_active:
            self.remove_pending(record_id)
            self._active.add(record_id)
            return True
        if record_id not in self._pending:
            self._pending.append(record_id)
        return False

    def release(self, record_id: str) -> list[str]:
        self._active.discard(record_id)
        self.remove_pending(record_id)
        return self._promote()

    def remove_pending(self, record_id: str) -> None:
        if record_id not in self._pending:
            return
        self._pending = deque(
            item for item in self._pending if item != record_id
        )


    def reorder_pending(self, ordered_ids) -> None:
        """Reorder only IDs already waiting in the in-memory queue."""
        requested = [str(item) for item in ordered_ids]
        existing = list(self._pending)
        existing_set = set(existing)
        ordered = [item for item in requested if item in existing_set]
        ordered.extend(item for item in existing if item not in set(ordered))
        self._pending = deque(ordered)

    def pause_all(self) -> None:
        self._active.clear()
        self._pending.clear()

    def set_max_active(self, value: int) -> list[str]:
        self._max_active = max(1, int(value))
        return self._promote()

    def _promote(self) -> list[str]:
        promoted: list[str] = []
        while self._pending and len(self._active) < self._max_active:
            record_id = self._pending.popleft()
            if record_id in self._active:
                continue
            self._active.add(record_id)
            promoted.append(record_id)
        return promoted
