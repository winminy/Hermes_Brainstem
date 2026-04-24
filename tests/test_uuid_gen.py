from __future__ import annotations

from datetime import datetime, timezone

from plugins.memory.hermes_memory.core.clock import FrozenClock
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator


def test_uuid_generator_adds_suffix_within_same_minute() -> None:
    generator = UUIDGenerator(clock=FrozenClock(datetime(2026, 4, 23, 10, 39, 5, tzinfo=timezone.utc)))

    values = [generator.generate() for _ in range(5)]

    assert values == [
        'obs:20260423T1039',
        'obs:20260423T1039-1',
        'obs:20260423T1039-2',
        'obs:20260423T1039-3',
        'obs:20260423T1039-4',
    ]
