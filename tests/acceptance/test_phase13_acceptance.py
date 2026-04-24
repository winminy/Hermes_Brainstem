from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
import threading
from typing import Any, cast

import anyio
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
import pytest

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec
from plugins.memory.hermes_memory.core.invariant_guard import GuardedWriter, InvariantViolationError
from plugins.memory.hermes_memory.inbox import DedupDecision, GraduationResult, InboxClassification, InboxRunner, InboxSourceEntry
from plugins.memory.hermes_memory.mcp.server import HermesMemoryMCPApplication
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline.persist_process import SyncBatchResult, SyncEntryResult


class FakeDeduplicator:
    def deduplicate(
        self,
        *,
        entry_path: Path,
        document: object,
        title: str,
        vault_root: Path,
        dry_run: bool = False,
    ) -> DedupDecision:
        del entry_path, document, title, vault_root, dry_run
        return DedupDecision(action='continue')


class BlockingClassifier:
    def __init__(self, *, started: threading.Event, release: threading.Event) -> None:
        self._started = started
        self._release = release

    def classify(self, *, title: str, document: object) -> InboxClassification:
        del title, document
        self._started.set()
        self._release.wait(timeout=5)
        return InboxClassification(
            status='success',
            title='Accepted',
            body='# Accepted',
            area='knowledge',
            note_type='memo',
            tags=('PKM',),
            reason=None,
            reason_tag=None,
        )


class FakeGraduator:
    def graduate(
        self,
        *,
        entry_path: Path,
        document: object,
        title: str,
        classification: InboxClassification,
        vault_root: Path,
        dry_run: bool = False,
    ) -> GraduationResult:
        del entry_path, document, title, classification, vault_root, dry_run
        return GraduationResult(status='written', knowledge_path='knowledge/Accepted.md', removed_inbox_path=None)


class FakePipeline:
    def full_sync(self, *, datasources: Sequence[str] | None = None, vault_root: Path | None = None, dry_run: bool = False) -> SyncBatchResult:
        del vault_root, dry_run
        return SyncBatchResult(mode='full', datasources=tuple(datasources or ('User Info DB',)), entries=(), counts={'written': 0})

    def incremental_sync(self, *, datasources: Sequence[str] | None = None, vault_root: Path | None = None, dry_run: bool = False) -> SyncBatchResult:
        del vault_root, dry_run
        return SyncBatchResult(mode='incremental', datasources=tuple(datasources or ('User Info DB',)), entries=(), counts={'written': 0})

    def process_single_entry(self, datasource: str, *, page_id: str | None = None, vault_root: Path | None = None, dry_run: bool = False) -> SyncEntryResult:
        del vault_root, dry_run
        return SyncEntryResult(
            datasource=datasource,
            source_page_id=page_id or 'unknown',
            status='written',
            relative_path='knowledge/Single.md',
            reason=None,
            quarantine_path=None,
            markdown='# Single',
        )


class FakeInboxRunner:
    def ingest(self, entry: InboxSourceEntry, *, vault_root: Path, dry_run: bool = False) -> Any:
        del vault_root, dry_run
        return {
            'status': 'written',
            'inbox_path': None,
            'knowledge_path': f'knowledge/{entry.title}.md',
            'quarantine_path': None,
            'reason': None,
            'reason_tag': None,
            'queue_path': None,
        }


class FakeLightRAGBackend:
    def upsert(self, documents: Sequence[object]) -> Mapping[str, object]:
        del documents
        return {'status': 'success'}

    def query_related(self, text: str, *, top_k: int) -> Sequence[object]:
        del text, top_k
        return []

    def delete(self, document_ids: Sequence[str]) -> Mapping[str, object]:
        del document_ids
        return {'status': 'deleted'}


@pytest.mark.acceptance
def test_acceptance_rejects_frontmatter_mutation() -> None:
    codec = FrontmatterCodec(ConfigLayer.from_settings(HermesMemorySettings()))
    existing = codec.loads(
        '---\n'
        'uuid: obs:20260424T0710\n'
        'area: knowledge\n'
        'type: memo\n'
        'tags:\n'
        '  - AI\n'
        'date: 2026-04-24\n'
        'updated: 2026-04-24\n'
        'source:\n'
        '  - session:phase13\n'
        'source_type: ""\n'
        'file_type: md\n'
        '---\n\n'
        'Original\n'
    )
    candidate = codec.loads(
        '---\n'
        'uuid: obs:20260424T0711\n'
        'area: knowledge\n'
        'type: memo\n'
        'tags:\n'
        '  - AI\n'
        'date: 2026-04-24\n'
        'updated: 2026-04-25\n'
        'source:\n'
        '  - session:phase13\n'
        'source_type: ""\n'
        'file_type: md\n'
        '---\n\n'
        'Changed\n'
    )

    with pytest.raises(InvariantViolationError, match='invariant field changed: uuid'):
        GuardedWriter(lambda document: document.body).write(candidate, existing=existing)


@pytest.mark.anyio
@pytest.mark.acceptance
async def test_acceptance_rejects_non_schema_mcp_input(tmp_path: Path) -> None:
    services = HermesMemoryServices(
        config=ConfigLayer.from_settings(HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', log_level='INFO')),
        lightrag_backend=cast(Any, FakeLightRAGBackend()),
        pipeline=cast(Any, FakePipeline()),
        inbox_runner=cast(Any, FakeInboxRunner()),
    )
    app = HermesMemoryMCPApplication(services=services)

    async with _client_session(app) as session:
        await session.initialize()
        with pytest.raises(McpError) as excinfo:
            await session.call_tool('search', {'query': 'invalid', 'top_k': 0})

    assert excinfo.value.error.code == -32602
    assert 'Input validation error' in excinfo.value.error.message


@pytest.mark.acceptance
def test_acceptance_rejects_parallel_inbox_processing_attempt(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    runner = InboxRunner(
        ConfigLayer.from_settings(HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', log_level='INFO')),
        deduplicator=cast(Any, FakeDeduplicator()),
        classifier=cast(Any, BlockingClassifier(started=started, release=release)),
        graduator=cast(Any, FakeGraduator()),
    )
    background_errors: list[BaseException] = []

    def run_batch() -> None:
        try:
            runner.run([InboxSourceEntry(title='first', body='# first', source=('session:first',))], vault_root=tmp_path)
        except BaseException as exc:  # pragma: no cover - asserted below
            background_errors.append(exc)

    thread = threading.Thread(target=run_batch)
    thread.start()
    assert started.wait(timeout=5)

    with pytest.raises(RuntimeError, match='parallel inbox processing is not allowed'):
        runner.run([InboxSourceEntry(title='second', body='# second', source=('session:second',))], vault_root=tmp_path)

    release.set()
    thread.join(timeout=5)
    assert not background_errors


@asynccontextmanager
async def _client_session(app: HermesMemoryMCPApplication) -> AsyncIterator[ClientSession]:
    server_read_send, server_read_recv = anyio.create_memory_object_stream(16)
    client_read_send, client_read_recv = anyio.create_memory_object_stream(16)
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(app.server.run, server_read_recv, client_read_send, app.server.create_initialization_options())
        async with ClientSession(client_read_recv, server_read_send) as session:
            yield session
        task_group.cancel_scope.cancel()
