"""A per-user limit on Copilot messages: at most a number per sliding minute.

The count lives in this process's memory. With several app processes each one counts on its own,
and a restart forgets; one process serves this app, so that is enough here.
"""

import time
from collections import deque
from collections.abc import Callable, Hashable

WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = per_minute
        self._clock = clock
        self._hits: dict[Hashable, deque[float]] = {}

    def allow(self, key: Hashable) -> bool:
        """Counts one message for the key, unless it has reached the limit in the last minute."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True
