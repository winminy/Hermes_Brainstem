from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings, SyncConfig
from plugins.memory.hermes_memory.hooks.notion_sync import run_notion_sync
import asyncio

from plugins.memory.hermes_memory.core.scheduler import InternalSyncScheduler, build_scheduler
from plugins.memory.hermes_memory.pipeline import SyncBatchResult


@dataclass(frozen=True, slots=True)
class FakeDatasourceSpec:
    name: str
    scan_mode: str | None


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def incremental_sync(self, *, datasources: tuple[str, ...], vault_root: Path, dry_run: bool) -> SyncBatchResult:
        self.calls.append({'datasources': datasources, 'vault_root': vault_root, 'dry_run': dry_run})
        return SyncBatchResult(mode='incremental', datasources=datasources, entries=(), counts={'written': len(datasources)})


class FakeNotionBackend:
    def __init__(self) -> None:
        self.datasources = {
            'Sub-task DB': FakeDatasourceSpec(name='Sub-task DB', scan_mode='daily_auto'),
            'User Info DB': FakeDatasourceSpec(name='User Info DB', scan_mode='daily_auto'),
            'Manual DB': FakeDatasourceSpec(name='Manual DB', scan_mode='manual_only'),
        }


class FakeServices:
    def __init__(self, config: ConfigLayer) -> None:
        self.config = config
        self.pipeline = FakePipeline()
        self.notion_backend = FakeNotionBackend()


def test_notion_sync_uses_incremental_pipeline_for_daily_datasources(tmp_path: Path) -> None:
    config = _config(tmp_path)
    services = FakeServices(config)

    result = run_notion_sync(services=cast(Any, services), vault_root=tmp_path)

    assert result.datasources == ('Sub-task DB', 'User Info DB')
    assert services.pipeline.calls == [
        {
            'datasources': ('Sub-task DB', 'User Info DB'),
            'vault_root': tmp_path,
            'dry_run': False,
        }
    ]
    assert result.sync_result.counts == {'written': 2}


def test_scheduler_internal_runs_on_startup_once(tmp_path: Path) -> None:
    config = ConfigLayer.from_settings(
        HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', timezone='UTC', log_level='INFO')
    )
    services = FakeServices(config)
    calls: list[str] = []

    async def run_once() -> None:
        calls.append('tick')

    async def fake_sleep(_: float) -> None:
        raise asyncio.CancelledError

    registered = build_scheduler(
        services=cast(Any, services),
        run_incremental_sync_once=run_once,
        sleep_func=fake_sleep,
    )

    assert registered.job_ids == ('incremental-sync',)
    assert isinstance(registered.scheduler, InternalSyncScheduler)

    async def exercise() -> None:
        registered.scheduler.start()
        await asyncio.sleep(0)
        registered.scheduler.shutdown()
        await asyncio.sleep(0)

    asyncio.run(exercise())
    assert calls == ['tick']


def test_scheduler_cron_mode_disables_internal_loop(tmp_path: Path) -> None:
    config = ConfigLayer.from_settings(
        HermesMemorySettings(
            vault_root=tmp_path,
            skills_root=tmp_path / 'skills',
            timezone='UTC',
            log_level='INFO',
            sync=SyncConfig(scheduler='cron', cron_expression='*/15 * * * *'),
        )
    )
    services = FakeServices(config)
    registered = build_scheduler(services=cast(Any, services))

    assert registered.job_ids == ()
    assert registered.scheduler.started is False
    registered.scheduler.start()
    assert registered.scheduler.started is True


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', timezone='UTC', log_level='INFO')
    return ConfigLayer.from_settings(settings)
