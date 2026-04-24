from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plugins.memory.hermes_memory.inbox import InboxSourceEntry
from plugins.memory.hermes_memory.mcp.errors import raise_invalid_params
from plugins.memory.hermes_memory.mcp.schema_loader import load_schema
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices

from .base import ManagedTool


def build_inbox_submit_tool(services: HermesMemoryServices) -> ManagedTool:
    def handler(arguments: Mapping[str, Any]) -> dict[str, Any]:
        vault_root = services.config.settings.vault_root
        if vault_root is None:
            raise_invalid_params('vault_root is not configured', data={'field': 'vault_root'})
        entry = InboxSourceEntry(
            title=_require_string(arguments.get('title'), field='title'),
            body=_require_string(arguments.get('body'), field='body'),
            source=_string_tuple(arguments.get('source'), field='source'),
            uuid=_optional_string(arguments.get('uuid')),
            source_type=_optional_string(arguments.get('source_type')) or '',
            file_type=_optional_string(arguments.get('file_type')) or 'md',
            tags=_string_tuple(arguments.get('tags'), field='tags'),
            note_type=_optional_string(arguments.get('note_type')) or 'memo',
            updated=_optional_string(arguments.get('updated')),
            date=_optional_string(arguments.get('date')),
        )
        result = services.inbox_runner.ingest(entry, vault_root=vault_root, dry_run=bool(arguments.get('dry_run', False)))
        return {
            'status': result.status,
            'inbox_path': result.inbox_path,
            'knowledge_path': result.knowledge_path,
            'quarantine_path': result.quarantine_path,
            'reason': result.reason,
            'reason_tag': result.reason_tag,
            'queue_path': result.queue_path,
        }

    return ManagedTool(
        name='inbox_submit',
        title='Hermes Inbox Submit',
        description='Phase 7 inbox entry submission wrapper.',
        input_schema=load_schema('inbox_submit.input.json'),
        output_schema=load_schema('inbox_submit.output.json'),
        handler=handler,
    )


def _require_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise_invalid_params(f'{field} must be a non-empty string', data={'field': field})
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise_invalid_params('expected a string value')
    stripped = value.strip()
    return stripped or None


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise_invalid_params(f'{field} must be an array of strings', data={'field': field})
    return tuple(item.strip() for item in value if item.strip())
