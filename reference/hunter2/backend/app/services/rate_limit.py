"""Small in-memory, per-user cooldowns for a single bot process."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic


@dataclass(slots=True)
class PerUserRateLimiter:
    """Track action timestamps without retaining Telegram profile information."""

    clock: Callable[[], float] = monotonic
    _last_actions: dict[tuple[int, str], float] = field(default_factory=dict)

    def allow(self, user_id: int, action: str, cooldown_seconds: float) -> bool:
        now = self.clock()
        key = (user_id, action)
        previous = self._last_actions.get(key)
        if previous is not None and now - previous < cooldown_seconds:
            return False
        self._last_actions[key] = now
        return True


