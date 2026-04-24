from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from plugins.memory.hermes_memory.mcp.errors import raise_invalid_params
from plugins.memory.hermes_memory.mcp.schema_loader import load_schema
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline.persist_process import SyncEntryResult

from .base import ManagedTool


def build_sync_tool(services: HermesMemoryServices) -> ManagedTool:
    def handler(arguments: Mapping[str, Any]) -> dict[str, Any]:
        mode = _require_enum(arguments.get('mode'), field='mode', values={'full', 'incremental', 'single'})
        dry_run = bool(arguments.get('dry_run', False))
        datasources = _string_tuple(arguments.get('datasources'))
        vault_root = services.config.settings.vault_root
        if vault_root is None:
            raise_invalid_params('vault_root is not configured', data={'field': 'vault_root'})
        if mode == 'full':
            result = services.pipeline.full_sync(datasources=datasources or None, vault_root=vault_root, dry_run=dry_run)
            return _batch_payload(result.mode, result.datasources, result.entries, result.counts)
        if mode == 'incremental':
            result = services.pipeline.incremental_sync(datasources=datasources or None, vault_root=vault_root, dry_run=dry_run)
            return _batch_payload(result.mode, result.datasources, result.entries, result.counts)
        datasource = _require_string(arguments.get('datasource'), field='datasource')
        page_id = _require_string(arguments.get('page_id'), field='page_id')
        entry = services.pipeline.process_single_entry(datasource, page_id=page_id, vault_root=vault_root, dry_run=dry_run)
        counts = dict(Counter([entry.status]))
        return _batch_payload('single', (datasource,), (entry,), counts)

    return ManagedTool(
        name='sync',
        title='Hermes Sync',
        description='Phase 6 pipeline sync wrapper for full, incremental, and single modes.',
        input_schema=load_schema('sync.input.json'),
        output_schema=load_schema('sync.output.json'),
        handler=handler,
    )


def _batch_payload(
    mode: str,
    datasources: tuple[str, ...],
    entries: tuple[SyncEntryResult, ...],
    counts: Mapping[str, int],
) -> dict[str, Any]:
    return {
        'mode': mode,
        'datasources': list(datasources),
        'counts': dict(counts),
        'entries': [
            {
                'datasource': entry.datasource,
                'source_page_id': entry.source_page_id,
                'status': entry.status,
                'relative_path': entry.relative_path,
                'reason': entry.reason,
                'quarantine_path': entry.quarantine_path,
                'markdown': entry.markdown,
            }
            for entry in entries
        ],
    }


def _require_enum(value: object, *, field: str, values: set[str]) -> str:
    resolved = _require_string(value, field=field)
    if resolved not in values:
        raise_invalid_params(f'{field} must be one of: {", ".join(sorted(values))}', data={'field': field})
    return resolved


def _require_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise_invalid_params(f'{field} must be a non-empty string', data={'field': field})
    return value.strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise_invalid_params('datasources must be an array of strings', data={'field': 'datasources'})
    return tuple(item.strip() for item in value if item.strip())
