from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import threading

from .clock import Clock, SystemClock


@dataclass(slots=True)
class UUIDGenerator:
    clock: Clock = field(default_factory=SystemClock)
    _counts: dict[str, int] = field(init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._counts = defaultdict(int)
        self._lock = threading.Lock()

    def generate(self) -> str:
        stamp = self.clock.now().strftime('%Y%m%dT%H%M')
        with self._lock:
            sequence = self._counts[stamp]
            self._counts[stamp] += 1
        if sequence == 0:
            return f'obs:{stamp}'
        return f'obs:{stamp}-{sequence}'


_default_generator = UUIDGenerator()


def generate_uuid(clock: Clock | None = None) -> str:
    if clock is None:
        return _default_generator.generate()
    return UUIDGenerator(clock=clock).generate()
