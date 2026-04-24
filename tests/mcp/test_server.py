from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate
from plugins.memory.hermes_memory.inbox import InboxProcessResult, InboxRunner, InboxSourceEntry
from plugins.memory.hermes_memory.mcp.server import HermesMemoryMCPApplication
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline.persist_process import PersistProcessPipeline, SyncBatchResult, SyncEntryResult


class FakeLightRAGBackend:
    def upsert(self, documents: Sequence[object]) -> dict[str, object]:
        del documents
        return {}

    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        del text, top_k
        return []

    def delete(self, document_ids: Sequence[str]) -> dict[str, object]:
        del document_ids
        return {}


class FakePipeline:
    def full_sync(self, *, datasources: Sequence[str] | None = None, vault_root: Path | None = None, dry_run: bool = False) -> SyncBatchResult:
        del vault_root, dry_run
        return SyncBatchResult(mode='full', datasources=tuple(datasources or ('User Info DB',)), entries=(), counts={'written': 0})

    def incremental_sync(self, *, datasources: Sequence[str] | None = None, vault_root: Path | None = None, dry_run: bool = False) -> SyncBatchResult:
        del vault_root, dry_run
        return SyncBatchResult(mode='incremental', datasources=tuple(datasources or ('User Info DB',)), entries=(), counts={'skipped': 0})

    def process_single_entry(self, datasource: str, *, page_id: str | None = None, vault_root: Path | None = None, dry_run: bool = False) -> SyncEntryResult:
        del vault_root, dry_run
        return SyncEntryResult(datasource=datasource, source_page_id=page_id or 'unknown', status='written', relative_path='knowledge/Single.md', reason=None, quarantine_path=None, markdown='# Single')


class FakeInboxRunner:
    def ingest(self, entry: InboxSourceEntry, *, vault_root: Path, dry_run: bool = False) -> InboxProcessResult:
        del vault_root, dry_run
        return InboxProcessResult(status='written', inbox_path=None, knowledge_path=f'knowledge/{entry.title}.md', quarantine_path=None, reason=None, reason_tag=None, queue_path=None)


@pytest.mark.anyio
async def test_mcp_roundtrip_lists_tools_and_calls_search_sync_inbox_status(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_note(config, tmp_path, 'knowledge/Searchable.md', body='# Searchable\n\nMemory MCP search works.')
    services = HermesMemoryServices(
        config=config,
        lightrag_backend=FakeLightRAGBackend(),
        pipeline=cast(PersistProcessPipeline, FakePipeline()),
        inbox_runner=cast(InboxRunner, FakeInboxRunner()),
    )
    app = HermesMemoryMCPApplication(services=services)

    async with _client_session(app) as session:
        await session.initialize()
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == {'search', 'sync', 'inbox_submit', 'status'}

        search_result = await session.call_tool('search', {'query': 'MCP', 'top_k': 5})
        assert search_result.structuredContent is not None
        assert search_result.structuredContent['count'] == 1
        assert search_result.structuredContent['hits'][0]['metadata']['title'] == 'Searchable'

        sync_result = await session.call_tool('sync', {'mode': 'single', 'datasource': 'User Info DB', 'page_id': 'page-1'})
        assert sync_result.structuredContent is not None
        assert sync_result.structuredContent['entries'][0]['relative_path'] == 'knowledge/Single.md'

        inbox_result = await session.call_tool('inbox_submit', {'title': 'Inbox note', 'body': 'Body', 'source': ['session:test-inbox']})
        assert inbox_result.structuredContent is not None
        assert inbox_result.structuredContent['knowledge_path'] == 'knowledge/Inbox note.md'

        status_result = await session.call_tool('status', {})
        assert status_result.structuredContent is not None
        assert status_result.structuredContent['healthy'] is True


@pytest.mark.anyio
async def test_mcp_invalid_params_return_jsonrpc_error_object(tmp_path: Path) -> None:
    config = _config(tmp_path)
    services = HermesMemoryServices(
        config=config,
        lightrag_backend=FakeLightRAGBackend(),
        pipeline=cast(PersistProcessPipeline, FakePipeline()),
        inbox_runner=cast(InboxRunner, FakeInboxRunner()),
    )
    app = HermesMemoryMCPApplication(services=services)

    async with _client_session(app) as session:
        await session.initialize()
        with pytest.raises(McpError) as excinfo:
            await session.call_tool('search', {'query': 'MCP', 'top_k': 0})

    assert excinfo.value.error.code == -32602
    assert 'Input validation error' in excinfo.value.error.message


@asynccontextmanager
async def _client_session(app: HermesMemoryMCPApplication) -> AsyncIterator[ClientSession]:
    server_read_send, server_read_recv = anyio.create_memory_object_stream(16)
    client_read_send, client_read_recv = anyio.create_memory_object_stream(16)
    async with anyio.create_task_group() as tg:
        tg.start_soon(app.server.run, server_read_recv, client_read_send, app.server.create_initialization_options())
        async with ClientSession(client_read_recv, server_read_send) as session:
            yield session
        tg.cancel_scope.cancel()


def _config(vault_root: Path) -> ConfigLayer:
    return ConfigLayer.from_settings(HermesMemorySettings(vault_root=vault_root, log_level='INFO'))


def _write_note(config: ConfigLayer, vault_root: Path, relative_path: str, *, body: str) -> None:
    path = vault_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = FrontmatterModel.from_data(
        {
            'uuid': 'obs:20260424T0600-1',
            'area': 'knowledge',
            'type': 'memo',
            'tags': ['AI'],
            'date': '2026-04-24',
            'updated': '2026-04-24',
            'source': ['session:test-mcp'],
            'source_type': '',
            'file_type': 'md',
        },
        tag_registry=config.tag_registry,
    )
    path.write_text(FrontmatterCodec(config).dumps(MarkdownDocument(frontmatter=frontmatter, body=body)), encoding='utf-8')