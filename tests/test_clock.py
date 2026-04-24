from __future__ import annotations

from datetime import datetime

import pytest

from plugins.memory.hermes_memory.core.clock import FrozenClock, SystemClock


def test_system_clock_returns_timezone_aware_datetime() -> None:
    now = SystemClock('UTC').now()
    assert now.tzinfo is not None


def test_frozen_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        FrozenClock(datetime(2026, 4, 23, 10, 39, 0)).now()
