from __future__ import annotations

import threading
from collections import deque
from pathlib import Path
from typing import Iterable


def _key(value: str | Path) -> str:
    return str(Path(value).resolve())


class PreemptiveTaskQueue:
    """Thread-safe file queue with a separate urgent lane.

    The worker owns ``current``.  UI actions may move a normal waiting file to
    the front of the urgent lane, or add a newly dropped file there.  When the
    current file is cooperatively paused, ``requeue_current`` places it before
    the remaining normal work but after every urgent file.
    """

    def __init__(
        self,
        paths: Iterable[str | Path],
        priority_paths: Iterable[str | Path] = (),
    ):
        priority_keys = {_key(value) for value in priority_paths}
        ordered: list[str] = []
        seen: set[str] = set()
        for value in paths:
            path = _key(value)
            if path in seen:
                continue
            seen.add(path)
            ordered.append(path)
        self._priority = deque(path for path in ordered if path in priority_keys)
        self._normal = deque(path for path in ordered if path not in priority_keys)
        self._completed: list[str] = []
        self._current: str | None = None
        self._accepting = True
        self._lock = threading.RLock()

    @property
    def current_path(self) -> str | None:
        with self._lock:
            return self._current

    @property
    def completed_count(self) -> int:
        with self._lock:
            return len(self._completed)

    @property
    def total_count(self) -> int:
        with self._lock:
            return (
                len(self._completed)
                + (1 if self._current else 0)
                + len(self._priority)
                + len(self._normal)
            )

    def pop_next(self) -> str | None:
        with self._lock:
            if self._current is not None:
                raise RuntimeError("The current task must be completed or requeued first.")
            if self._priority:
                self._current = self._priority.popleft()
            elif self._normal:
                self._current = self._normal.popleft()
            else:
                self._accepting = False
                return None
            return self._current

    def prioritize(self, value: str | Path) -> tuple[bool, bool]:
        """Move/add a file to the urgent lane.

        Returns ``(accepted, added)``. ``added`` is true when the path was not
        already part of the active run.
        """

        path = _key(value)
        with self._lock:
            if not self._accepting or path == self._current or path in self._completed:
                return False, False
            added = path not in self._priority and path not in self._normal
            try:
                self._priority.remove(path)
            except ValueError:
                pass
            try:
                self._normal.remove(path)
            except ValueError:
                pass
            self._priority.appendleft(path)
            return True, added

    def complete_current(self, expected: str | Path) -> None:
        path = _key(expected)
        with self._lock:
            if self._current != path:
                raise RuntimeError("Completed task does not match the current task.")
            self._completed.append(path)
            self._current = None

    def requeue_current(self, expected: str | Path) -> None:
        """Resume the interrupted file after all urgent work."""

        path = _key(expected)
        with self._lock:
            if self._current != path:
                raise RuntimeError("Interrupted task does not match the current task.")
            self._current = None
            if path not in self._normal and path not in self._priority:
                self._normal.appendleft(path)

    def remove(self, value: str | Path) -> bool:
        """Remove a waiting file without disturbing the current file."""

        path = _key(value)
        with self._lock:
            if path == self._current or path in self._completed:
                return False
            for lane in (self._priority, self._normal):
                try:
                    lane.remove(path)
                    return True
                except ValueError:
                    continue
            return False

    def snapshot(self) -> list[str]:
        with self._lock:
            values = list(self._completed)
            if self._current:
                values.append(self._current)
            values.extend(self._priority)
            values.extend(self._normal)
            return values

    def pending_snapshot(self) -> list[str]:
        with self._lock:
            return [*self._priority, *self._normal]
