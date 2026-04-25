from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from mcp.shared.exceptions import McpError

from plugins.memory.hermes_memory.inbox import InboxRunner
from plugins.memory.hermes_memory.mcp.server import HermesMemoryMCPApplication
from plugins.memory.hermes_memory.mcp.schema_loader import load_schema
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline.persist_process import PersistProcessPipeline
from tests.mcp.test_server import FakeInboxRunner, FakeLightRAGBackend, FakePipeline, _client_session, _config


@pytest.mark.anyio
async def test_sync_single_mode_runtime_validation_still_requires_datasource_and_page_id(tmp_path: Path) -> None:
    services = HermesMemoryServices(
        config=_config(tmp_path),
        lightrag_backend=FakeLightRAGBackend(),
        pipeline=cast(PersistProcessPipeline, FakePipeline()),
        inbox_runner=cast(InboxRunner, FakeInboxRunner()),
    )
    app = HermesMemoryMCPApplication(services=services)

    async with _client_session(app) as session:
        await session.initialize()
        with pytest.raises(McpError) as excinfo:
            await session.call_tool('sync', {'mode': 'single'})

    assert excinfo.value.error.code == -32602
    assert 'datasource must be a non-empty string' in excinfo.value.error.message


def test_input_schemas_avoid_top_level_openai_incompatible_keywords() -> None:
    schema_dir = Path(__file__).resolve().parents[2] / 'code' / 'plugins' / 'memory' / 'hermes_memory' / 'mcp' / 'schemas'

    for schema_path in sorted(schema_dir.glob('*.input.json')):
        schema = load_schema(schema_path.name)
        assert schema.get('type') == 'object'
        assert _find_forbidden_keyword_path(schema, {'allOf', 'anyOf', 'oneOf', 'enum', 'not'}) is None


def test_all_schemas_avoid_openai_incompatible_keywords_anywhere() -> None:
    schema_dir = Path(__file__).resolve().parents[2] / 'code' / 'plugins' / 'memory' / 'hermes_memory' / 'mcp' / 'schemas'

    for schema_path in sorted(schema_dir.glob('*.json')):
        schema = load_schema(schema_path.name)
        assert _find_forbidden_keyword_path(schema, {'allOf', 'anyOf', 'oneOf', 'enum'}) is None


def _find_forbidden_keyword_path(payload: object, forbidden: set[str], path: str = '$') -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden:
                return f'{path}.{key}'
            found = _find_forbidden_keyword_path(value, forbidden, f'{path}.{key}')
            if found is not None:
                return found
        return None
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            found = _find_forbidden_keyword_path(item, forbidden, f'{path}[{index}]')
            if found is not None:
                return found
    return None
