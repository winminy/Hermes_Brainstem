from __future__ import annotations

from pathlib import Path

import pytest

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.hooks.scheduler import RegisteredScheduler
from plugins.memory.hermes_memory.mcp.server import HermesMemoryMCPApplication
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices


class FakeScheduler:
    def __init__(self) -> None:
        self.start_calls = 0
        self.shutdown_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1


@pytest.mark.anyio
async def test_scheduler_lifecycle_is_owned_by_mcp_server(tmp_path: Path) -> None:
    services = HermesMemoryServices(
        config=ConfigLayer.from_settings(
            HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', log_level='INFO')
        )
    )
    scheduler = FakeScheduler()
    app = HermesMemoryMCPApplication(
        services=services,
        scheduler_factory=lambda current_services: RegisteredScheduler(scheduler=scheduler, job_ids=()),
    )

    async with app.scheduler_lifespan():
        assert scheduler.start_calls == 1
        assert scheduler.shutdown_calls == 0

    assert scheduler.start_calls == 1
    assert scheduler.shutdown_calls == 1
