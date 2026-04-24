from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime:
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    timezone_name: str = 'UTC'

    def now(self) -> datetime:
        return datetime.now(tz=ZoneInfo(self.timezone_name))


@dataclass(frozen=True, slots=True)
class FrozenClock:
    current: datetime

    def now(self) -> datetime:
        if self.current.tzinfo is None:
            raise ValueError('FrozenClock requires a timezone-aware datetime')
        return self.current
