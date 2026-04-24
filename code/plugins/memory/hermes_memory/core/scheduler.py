from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugins.memory.hermes_memory.core.sync import run_incremental_sync


@dataclass(frozen=True, slots=True)
class RegisteredScheduler:
    scheduler: Any
    job_ids: tuple[str, ...]


class DisabledSyncScheduler:
    def __init__(self, message: str) -> None:
        self.message = message
        self.started = False
        self.shutdown_called = False

    def start(self) -> None:
        self.started = True
        print(self.message)

    def shutdown(self) -> None:
        self.shutdown_called = True


class InternalSyncScheduler:
    def __init__(
        self,
        *,
        interval_minutes: int,
        on_startup: bool,
        run_once: Callable[[], Awaitable[None] | None],
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.interval_minutes = interval_minutes
        self.on_startup = on_startup
        self._run_once = run_once
        self._sleep_func = sleep_func or asyncio.sleep
        self._task: asyncio.Task[None] | None = None
        self.started = False
        self.shutdown_called = False

    def start(self) -> None:
        if self._task is not None:
            return
        self.started = True
        self._task = asyncio.create_task(self._loop(), name='hermes-memory-sync-scheduler')

    def shutdown(self) -> None:
        self.shutdown_called = True
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        try:
            if self.on_startup:
                await _maybe_await(self._run_once())
            while True:
                await self._sleep_func(float(self.interval_minutes * 60))
                await _maybe_await(self._run_once())
        except asyncio.CancelledError:
            return


async def _maybe_await(result: Awaitable[None] | None) -> None:
    if result is not None:
        await result


def build_scheduler(
    *,
    services: Any,
    last_sync_path: Path | None = None,
    run_incremental_sync_once: Callable[[], Awaitable[None] | None] | None = None,
    sleep_func: Callable[[float], Awaitable[None]] | None = None,
) -> RegisteredScheduler:
    sync_config = services.config.settings.sync
    if sync_config.scheduler == 'cron':
        return RegisteredScheduler(
            scheduler=DisabledSyncScheduler('sync.scheduler=cron — 외부 cron으로 동기화 중'),
            job_ids=(),
        )

    runner = run_incremental_sync_once
    if runner is None:

        def runner() -> Awaitable[None]:
            return _run_incremental_sync(services=services, last_sync_path=last_sync_path)

    scheduler = InternalSyncScheduler(
        interval_minutes=sync_config.interval_minutes,
        on_startup=sync_config.on_startup,
        run_once=runner,
        sleep_func=sleep_func,
    )
    return RegisteredScheduler(scheduler=scheduler, job_ids=('incremental-sync',))


async def _run_incremental_sync(*, services: Any, last_sync_path: Path | None) -> None:
    run_incremental_sync(services, last_sync_path=last_sync_path)


__all__ = ['DisabledSyncScheduler', 'InternalSyncScheduler', 'RegisteredScheduler', 'build_scheduler']
