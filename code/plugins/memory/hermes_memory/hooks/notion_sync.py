from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.hooks.common import parse_hook_payload, require_vault_root, resolve_services
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline import SyncBatchResult


@dataclass(frozen=True, slots=True)
class NotionSyncHookResult:
    datasources: tuple[str, ...]
    sync_result: SyncBatchResult


def run_notion_sync(
    *,
    session_id: str | None = None,
    conversation_history: object | None = None,
    model: str | None = None,
    platform: str | None = None,
    services: HermesMemoryServices | None = None,
    config: ConfigLayer | None = None,
    vault_root: Path | None = None,
    dry_run: bool = False,
    datasources: Sequence[str] | None = None,
) -> NotionSyncHookResult:
    parse_hook_payload(
        session_id=session_id,
        conversation_history=conversation_history,
        model=model,
        platform=platform,
    )
    resolved_services = resolve_services(services=services, config=config)
    resolved_vault_root = require_vault_root(resolved_services, vault_root=vault_root)
    resolved_datasources = tuple(datasources) if datasources is not None else _resolve_daily_datasources(resolved_services)
    sync_result = resolved_services.pipeline.incremental_sync(
        datasources=resolved_datasources,
        vault_root=resolved_vault_root,
        dry_run=dry_run,
    )
    return NotionSyncHookResult(datasources=resolved_datasources, sync_result=sync_result)


def _resolve_daily_datasources(services: HermesMemoryServices) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for spec in services.notion_backend.datasources.values():
        if spec.name in seen:
            continue
        if spec.scan_mode != 'daily_auto':
            continue
        seen.add(spec.name)
        names.append(spec.name)
    return tuple(names)


__all__ = ['NotionSyncHookResult', 'run_notion_sync']
