from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, cast

import anyio
from mcp.client.session import ClientSession
import pytest

from plugins.memory.hermes_memory.attach import DownloadedAttachment, PersistAttachPipeline
from plugins.memory.hermes_memory.backends.lightrag import LightRAGDocument
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.converters import ConversationBinaryConverter, NotionBlockConverter
from plugins.memory.hermes_memory.core.clock import FrozenClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate
from plugins.memory.hermes_memory.hooks.quarantine_sweep import run_quarantine_sweep
from plugins.memory.hermes_memory.hooks.session_close import run_session_close
from plugins.memory.hermes_memory.inbox import (
    InboxClassification,
    InboxDeduplicator,
    InboxGraduator,
    InboxProcessResult,
    InboxRunner,
    InboxSourceEntry,
)
from plugins.memory.hermes_memory.mcp.server import HermesMemoryMCPApplication
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline import PersistProcessPipeline, PipelineCommitter, PipelineDispatcher, StructuredEntryReducer
from plugins.memory.hermes_memory.pipeline.persist_process import SyncBatchResult, SyncEntryResult


class FakeDataSources:
    def __init__(self, pages_by_db: Mapping[str, Sequence[dict[str, object]]]) -> None:
        self._pages_by_db = {key: [dict(page) for page in value] for key, value in pages_by_db.items()}

    def query(self, *, data_source_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        del page_size, start_cursor
        return {
            'results': [dict(page) for page in self._pages_by_db.get(data_source_id, ())],
            'has_more': False,
            'next_cursor': None,
        }


class FakePages:
    def __init__(self, pages: Mapping[str, dict[str, object]]) -> None:
        self._pages = {key: dict(value) for key, value in pages.items()}

    def retrieve(self, *, page_id: str) -> dict[str, object]:
        page = self._pages.get(page_id)
        if page is None:
            raise KeyError(page_id)
        return dict(page)


class FakeBlockChildren:
    def __init__(self, blocks_by_page: Mapping[str, Sequence[dict[str, object]]]) -> None:
        self._blocks_by_page = {key: [dict(block) for block in value] for key, value in blocks_by_page.items()}

    def list(self, *, block_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        del page_size, start_cursor
        return {
            'results': [dict(block) for block in self._blocks_by_page.get(block_id, ())],
            'has_more': False,
            'next_cursor': None,
        }


class FakeBlocks:
    def __init__(self, blocks_by_page: Mapping[str, Sequence[dict[str, object]]]) -> None:
        self.children = FakeBlockChildren(blocks_by_page)


class FakeNotionClient:
    def __init__(
        self,
        *,
        pages_by_db: Mapping[str, Sequence[dict[str, object]]],
        pages: Mapping[str, dict[str, object]],
        blocks_by_page: Mapping[str, Sequence[dict[str, object]]] | None = None,
    ) -> None:
        self.data_sources = FakeDataSources(pages_by_db)
        self.pages = FakePages(pages)
        self.blocks = FakeBlocks(blocks_by_page or {})


class MockStructuredLLM:
    def __init__(self, *, fail_ids: set[str] | None = None) -> None:
        self.fail_ids = fail_ids or set()

    def generate(self, request: Any) -> Mapping[str, object]:
        payload = json.loads(request.user_prompt.split('PAYLOAD:\n', 1)[1])
        source_page_id = str(payload['source_page_id'])
        if source_page_id in self.fail_ids:
            raise RuntimeError(f'synthetic reduce failure for {source_page_id}')
        title = str(payload['title_hint'])
        return {
            'title': title,
            'body': f'# {title}\n\n## Summary\n- source_page_id: {source_page_id}',
            'frontmatter': dict(payload['seed_frontmatter']),
        }


class DummyEmbeddingBackend:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        self.calls.append(batch)
        return [[0.1, 0.2, 0.3] for _ in batch]

    def embed_query(self, text: str) -> list[float]:
        del text
        return [0.1, 0.2, 0.3]


class RecordingLightRAGBackend:
    def __init__(
        self,
        *,
        candidates: Sequence[LightRAGCandidate] = (),
        fail_query: bool = False,
    ) -> None:
        self.candidates = list(candidates)
        self.fail_query = fail_query
        self.upserts: list[list[LightRAGDocument]] = []

    def upsert(self, documents: Sequence[LightRAGDocument]) -> Mapping[str, object]:
        batch = list(documents)
        self.upserts.append(batch)
        return {'status': 'success', 'count': len(batch)}

    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        del text, top_k
        if self.fail_query:
            raise RuntimeError('LightRAG fallback mode engaged')
        return list(self.candidates)

    def delete(self, document_ids: Sequence[str]) -> Mapping[str, object]:
        del document_ids
        return {'status': 'deleted'}


class MockAttachmentDownloader:
    def __init__(self, payloads: Mapping[str, DownloadedAttachment]) -> None:
        self._payloads = dict(payloads)

    def download(self, attachment: Any) -> DownloadedAttachment:
        return self._payloads[str(attachment.attachment_id)]


class StaticClassifier:
    def __init__(self, by_title: Mapping[str, InboxClassification]) -> None:
        self._by_title = dict(by_title)

    def classify(self, *, title: str, document: object) -> InboxClassification:
        del document
        return self._by_title[title]


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
    def ingest(self, entry: InboxSourceEntry, *, vault_root: Path, dry_run: bool = False) -> InboxProcessResult:
        del vault_root, dry_run
        return InboxProcessResult(
            status='written',
            inbox_path=None,
            knowledge_path=f'knowledge/{entry.title}.md',
            quarantine_path=None,
            reason=None,
            reason_tag=None,
            queue_path=None,
        )


@pytest.mark.e2e
def test_e2e_full_sync_happy_path(tmp_path: Path) -> None:
    pipeline, _, embedding_backend, lightrag_backend = _build_process_pipeline(tmp_path)

    first = pipeline.full_sync(vault_root=tmp_path)
    second = pipeline.full_sync(vault_root=tmp_path)

    assert first.counts == {'written': 3}
    assert second.counts == {'unchanged': 3}
    assert len(sorted((tmp_path / 'knowledge').glob('*.md'))) == 3
    assert len(lightrag_backend.upserts) == 3
    assert len(embedding_backend.calls) == 6
    assert (tmp_path / 'knowledge' / '사용자 기본 정보.md').exists()


@pytest.mark.e2e
def test_e2e_incremental_sync_attach_and_sha256_dedup(tmp_path: Path) -> None:
    pipeline, client, _, _ = _build_process_pipeline(tmp_path)

    initial = pipeline.full_sync(vault_root=tmp_path)
    assert initial.counts == {'written': 3}

    updated_pages = _sample_pages()
    updated_pages['${USER_INFO_DB_ID}'][0]['last_edited_time'] = '2026-04-25T10:00:00.000Z'
    client.data_sources = FakeDataSources(updated_pages)
    incremental = pipeline.incremental_sync(vault_root=tmp_path)
    assert incremental.counts == {'skipped': 2, 'updated': 1}

    notion_backend = NotionBackend(config=_config(tmp_path), client=_attach_notion_client())
    downloader = MockAttachmentDownloader(
        {'block-pdf-1': DownloadedAttachment(payload=b'same-pdf-bytes', media_type='application/pdf')}
    )
    attach_pipeline = PersistAttachPipeline(
        config=_config(tmp_path),
        downloader=downloader,
        notion_backend=notion_backend,
        clock=_clock(),
    )

    first_attach = attach_pipeline.process_notion_page(
        'User Info DB',
        page_id='page-attach',
        scope='skill',
        skill_name='persist_attach',
    )
    second_attach = attach_pipeline.process_notion_page(
        'User Info DB',
        page_id='page-attach',
        scope='skill',
        skill_name='persist_attach',
    )

    assert first_attach.results[0].status == 'written'
    assert second_attach.results[0].status == 'deduplicated'
    assert first_attach.results[0].sha256 == sha256_hexdigest(b'same-pdf-bytes')
    assert first_attach.results[0].sha256 == second_attach.results[0].sha256
    assert first_attach.results[0].raw_path == second_attach.results[0].raw_path
    references_root = _config(tmp_path).skill_root() / 'persist_attach' / 'references'
    assert len(list(references_root.glob('*.pdf'))) == 1
    assert len(list(references_root.glob('*.md'))) == 1


@pytest.mark.e2e
def test_e2e_inbox_flow_and_session_close_merge_confirm(tmp_path: Path) -> None:
    config = _config(tmp_path)
    candidate_path = 'knowledge/Existing Match.md'
    _write_note(
        config,
        tmp_path,
        candidate_path,
        uuid='obs:20260424T0700-1',
        area='knowledge',
        note_type='memo',
        tags=('PKM',),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:existing-match',),
        source_type='',
        file_type='md',
        body='# Existing Match\n\n## Summary\n- existing note',
    )
    lightrag_backend = RecordingLightRAGBackend(
        candidates=[LightRAGCandidate(title='Existing Match', path=candidate_path, score=0.95, type='knowledge')]
    )
    notion_backend = NotionBackend(config=config, client=FakeNotionClient(pages_by_db={}, pages={}))
    embedding_backend = DummyEmbeddingBackend()
    pipeline = PersistProcessPipeline(
        config=config,
        notion_backend=notion_backend,
        reducer=StructuredEntryReducer(config=config, llm_backend=MockStructuredLLM(), clock=_clock()),
        embedding_backend=embedding_backend,
        lightrag_backend=lightrag_backend,
        dispatcher=PipelineDispatcher(config),
        committer=PipelineCommitter(config=config, lightrag_backend=lightrag_backend, clock=_clock()),
        clock=_clock(),
    )
    runner = InboxRunner(
        config,
        deduplicator=InboxDeduplicator(config, lightrag_backend=lightrag_backend, clock=_clock()),
        classifier=cast(
            Any,
            StaticClassifier(
                {
                    'Potential Merge': InboxClassification(
                        status='success',
                        title='Merged Knowledge',
                        body='# Merged Knowledge\n\n## Summary\n- confirmed on session close',
                        area='knowledge',
                        note_type='memo',
                        tags=('PKM',),
                        reason=None,
                        reason_tag=None,
                    )
                }
            ),
        ),
        graduator=InboxGraduator(config, pipeline=pipeline),
        notion_backend=notion_backend,
        pipeline=pipeline,
        clock=_clock(),
    )

    queued = runner.ingest(
        InboxSourceEntry(title='Potential Merge', body='# Potential Merge', source=('session:merge',)),
        vault_root=tmp_path,
    )

    assert queued.status == 'queued-merge'
    assert queued.queue_path is not None
    queue_path = Path(queued.queue_path)
    assert queue_path.exists()
    assert (tmp_path / 'inbox' / 'Potential Merge.md').exists()

    services = HermesMemoryServices(
        config=config,
        notion_backend=notion_backend,
        embedding_backend=embedding_backend,
        lightrag_backend=lightrag_backend,
        pipeline=pipeline,
        inbox_runner=runner,
    )
    result = run_session_close(
        session_id='sess-merge-confirm',
        conversation_history=[
            {'attachments': [{'file_id': 'knowledge-file', 'scope': 'knowledge'}, {'file_id': 'skill-file', 'scope': 'skill'}]}
        ],
        model='gpt-5.4',
        platform='discord',
        services=services,
        vault_root=tmp_path,
    )

    assert result.entries[0].merge_queue_action == 'consumed-promoted'
    assert result.entries[0].knowledge_path == 'knowledge/Merged Knowledge.md'
    assert result.audited_file_hashes == (sha256_hexdigest('knowledge-file'),)
    assert not queue_path.exists()
    assert (tmp_path / 'knowledge' / 'Merged Knowledge.md').exists()
    assert Path(result.audit_path).exists()


@pytest.mark.anyio
@pytest.mark.e2e
async def test_e2e_search_round_trip_via_mcp_with_semantic_fallback_and_filters(tmp_path: Path) -> None:
    config = _config(tmp_path)
    alpha_path = _write_note(
        config,
        tmp_path,
        'knowledge/Alpha.md',
        uuid='obs:20260424T0700-2',
        area='knowledge',
        note_type='knowledge',
        tags=('AI', '개발'),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:alpha',),
        source_type='',
        file_type='md',
        body='# Alpha\n\nSemantic vector search keeps long-term knowledge discoverable.',
    )
    _write_note(
        config,
        tmp_path,
        'knowledge/Beta.md',
        uuid='obs:20260424T0700-3',
        area='knowledge',
        note_type='memo',
        tags=('AI', 'PKM'),
        date='2026-04-24',
        updated='2026-04-25',
        source=('notion:beta',),
        source_type='notion',
        file_type='md',
        body='# Beta\n\nSearch notes mention semantic retrieval as a fallback strategy.',
    )
    hidden_path = _write_note(
        config,
        tmp_path,
        '_quarantine/2026-04/Hidden.md',
        uuid='obs:20260424T0700-4',
        area='knowledge',
        note_type='memo',
        tags=('AI',),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:hidden',),
        source_type='',
        file_type='md',
        body='# Hidden\n\nThis quarantined note must never appear.',
    )
    lightrag_backend = RecordingLightRAGBackend(
        candidates=[
            LightRAGCandidate(title='Hidden', path=str(hidden_path), score=0.99, type='memo'),
            LightRAGCandidate(title='Alpha', path=str(alpha_path), score=0.93, type='knowledge'),
        ]
    )
    services = HermesMemoryServices(
        config=config,
        lightrag_backend=lightrag_backend,
        pipeline=cast(PersistProcessPipeline, FakePipeline()),
        inbox_runner=cast(InboxRunner, FakeInboxRunner()),
    )
    app = HermesMemoryMCPApplication(services=services)

    async with _client_session(app) as session:
        await session.initialize()
        tools = await session.list_tools()
        assert any(tool.name == 'search' for tool in tools.tools)

        semantic_result = await session.call_tool(
            'search',
            {'query': 'semantic search', 'top_k': 2, 'filters': {'area': 'knowledge', 'tags': ['AI']}},
        )
        semantic_payload = cast(dict[str, Any], semantic_result.structuredContent)
        assert [hit['metadata']['title'] for hit in semantic_payload['hits']] == ['Alpha', 'Beta']
        assert semantic_payload['hits'][0]['origin'] == 'semantic'
        assert all(hit['metadata']['title'] != 'Hidden' for hit in semantic_payload['hits'])

        lightrag_backend.fail_query = True
        fallback_result = await session.call_tool(
            'search',
            {'query': 'fallback strategy', 'top_k': 3, 'filters': {'source_type': 'notion'}},
        )
        fallback_payload = cast(dict[str, Any], fallback_result.structuredContent)
        assert fallback_payload['requested_mode'] == 'semantic'
        assert [hit['metadata']['title'] for hit in fallback_payload['hits']] == ['Beta']
        assert all(hit['origin'] == 'direct_file' for hit in fallback_payload['hits'])

        direct_result = await session.call_tool(
            'search',
            {
                'query': 'search',
                'mode': 'direct',
                'top_k': 5,
                'filters': {'area': 'knowledge', 'tags': ['개발', 'PKM'], 'tag_match_mode': 'any'},
            },
        )
        direct_payload = cast(dict[str, Any], direct_result.structuredContent)
        assert [hit['metadata']['title'] for hit in direct_payload['hits']] == ['Alpha', 'Beta']


@pytest.mark.e2e
def test_e2e_quarantine_path_and_quarantine_sweep(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_note(
        config,
        tmp_path,
        'knowledge/Clean.md',
        uuid='obs:20260424T0700-5',
        area='knowledge',
        note_type='memo',
        tags=(),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:clean',),
        source_type='',
        file_type='md',
        body='# Clean\n\nAll good.',
    )
    invalid_path = tmp_path / 'inbox' / 'Broken.md'
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(
        '---\n'
        'uuid: obs:20260424T0700-6\n'
        'area: system\n'
        'type: memo\n'
        'tags: []\n'
        'date: 2026-04-24\n'
        'updated: 2026-04-24\n'
        'source:\n'
        '- session:broken\n'
        'source_type: ""\n'
        'file_type: md\n'
        '---\n\n'
        'Broken body\n',
        encoding='utf-8',
    )

    services = HermesMemoryServices(config=config, lightrag_backend=RecordingLightRAGBackend())
    result = run_quarantine_sweep(services=services, vault_root=tmp_path)

    quarantined = next(entry for entry in result.entries if entry.relative_path == 'inbox/Broken.md')
    assert quarantined.status == 'quarantined'
    assert quarantined.quarantine_path is not None
    quarantined_path = Path(quarantined.quarantine_path)
    assert quarantined_path.exists()
    assert quarantined_path.parent.parent == tmp_path / '_quarantine'
    assert quarantined_path.with_suffix('.md.reason.txt').exists()
    assert not invalid_path.exists()
    assert Path(result.audit_path).exists()


@pytest.mark.e2e
def test_e2e_converter_fidelity(tmp_path: Path) -> None:
    config = _config(tmp_path)
    notion_sample = _load_json_fixture('notion_row_sample.json')
    conversation_sample = _load_json_fixture('conversation_sample.json')

    notion_converter = NotionBlockConverter(config, clock=_clock())
    notion_artifact = notion_converter.convert_page(
        page=cast(dict[str, Any], notion_sample['page']),
        blocks=cast(list[dict[str, Any]], notion_sample['blocks']),
        tags=('AI',),
    )
    round_trip_blocks = notion_converter.document_to_notion_blocks(notion_artifact.markdown)

    conversation_converter = ConversationBinaryConverter(config, clock=_clock())
    session_artifact = conversation_converter.convert_session(
        session_id=cast(str, conversation_sample['session_id']),
        conversation_history=conversation_sample['conversation_history'],
        model=cast(str, conversation_sample['model']),
        platform=cast(str, conversation_sample['platform']),
        tags=('AI',),
    )
    attachment_artifacts = conversation_converter.extract_attachments(
        session_id=cast(str, conversation_sample['session_id']),
        conversation_history=conversation_sample['conversation_history'],
    )

    assert notion_artifact.frontmatter.source == ('notion:page-123',)
    assert '**bold**' in notion_artifact.body
    assert '[[Project Atlas]]' in notion_artifact.body
    assert '![[diagram.png]]' in notion_artifact.body
    assert '### Deep details' not in notion_artifact.body
    assert round_trip_blocks[0]['type'] == 'heading_1'
    assert round_trip_blocks[1]['type'] == 'heading_2'
    assert any(block['type'] == 'table' for block in round_trip_blocks)

    assert session_artifact.frontmatter.source == ('session:sess-42',)
    assert 'This raw transcript must not be persisted.' not in session_artifact.body
    assert '- attachment_count: 2' in session_artifact.body
    assert [artifact.filename for artifact in attachment_artifacts] == ['screenshot.png', 'spec.pdf']


@pytest.mark.e2e
def test_e2e_error_resilience_one_entry_fails_and_others_succeed(tmp_path: Path) -> None:
    pipeline, _, _, lightrag_backend = _build_process_pipeline(tmp_path, fail_ids={'page-2'})

    result = pipeline.full_sync(vault_root=tmp_path)

    assert result.counts == {'quarantined': 1, 'written': 2}
    assert len(sorted((tmp_path / 'knowledge').glob('*.md'))) == 2
    assert len(list((tmp_path / '_quarantine').rglob('*.json'))) == 1
    assert len(list((tmp_path / '_quarantine').rglob('*.txt'))) == 1
    assert len(lightrag_backend.upserts) == 2


@asynccontextmanager
async def _client_session(app: HermesMemoryMCPApplication) -> AsyncIterator[ClientSession]:
    server_read_send, server_read_recv = anyio.create_memory_object_stream(16)
    client_read_send, client_read_recv = anyio.create_memory_object_stream(16)
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(app.server.run, server_read_recv, client_read_send, app.server.create_initialization_options())
        async with ClientSession(client_read_recv, server_read_send) as session:
            yield session
        task_group.cancel_scope.cancel()


def _build_process_pipeline(
    vault_root: Path,
    *,
    fail_ids: set[str] | None = None,
) -> tuple[PersistProcessPipeline, FakeNotionClient, DummyEmbeddingBackend, RecordingLightRAGBackend]:
    config = _config(vault_root)
    client = FakeNotionClient(pages_by_db=_sample_pages(), pages={'proj-1': _relation_page('proj-1', 'Project Atlas')})
    notion_backend = NotionBackend(config=config, client=client)
    embedding_backend = DummyEmbeddingBackend()
    lightrag_backend = RecordingLightRAGBackend()
    reducer = StructuredEntryReducer(config=config, llm_backend=MockStructuredLLM(fail_ids=fail_ids), clock=_clock())
    committer = PipelineCommitter(config=config, lightrag_backend=lightrag_backend, clock=_clock())
    pipeline = PersistProcessPipeline(
        config=config,
        notion_backend=notion_backend,
        reducer=reducer,
        embedding_backend=embedding_backend,
        lightrag_backend=lightrag_backend,
        dispatcher=PipelineDispatcher(config),
        committer=committer,
        clock=_clock(),
    )
    return pipeline, client, embedding_backend, lightrag_backend


def _config(vault_root: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=vault_root, skills_root=vault_root / 'skills', timezone='UTC', log_level='INFO')
    return ConfigLayer.from_settings(settings)


def _clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 4, 24, 7, 0, tzinfo=timezone.utc))


def _sample_pages() -> dict[str, list[dict[str, object]]]:
    return {
        '${SUB_TASK_DB_ID}': [
            _page('page-1', '프로젝트 메모', '메모/ 리소스'),
            _page('page-2', '백로그 정리', 'Project Backlogs'),
        ],
        '${USER_INFO_DB_ID}': [
            _page('page-3', '사용자 기본 정보', '기본 정보'),
        ],
    }


def _page(page_id: str, title: str, notion_type: str) -> dict[str, object]:
    return {
        'id': page_id,
        'url': f'https://www.notion.so/{page_id}',
        'created_time': '2026-04-23T08:35:00.000Z',
        'last_edited_time': '2026-04-24T09:00:00.000Z',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': title}]},
            '유형': {'type': 'select', 'select': {'name': notion_type}},
            '프로젝트': {'type': 'relation', 'relation': []},
        },
    }


def _relation_page(page_id: str, title: str) -> dict[str, object]:
    return {'id': page_id, 'properties': {'Name': {'type': 'title', 'title': [{'plain_text': title}]}}}


def _attach_notion_client() -> FakeNotionClient:
    page: dict[str, object] = {
        'id': 'page-attach',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': 'Project Atlas'}]},
        },
    }
    blocks: list[dict[str, object]] = [
        {
            'id': 'block-pdf-1',
            'type': 'pdf',
            'pdf': {
                'type': 'file',
                'file': {'url': 'https://example.test/files/spec.pdf', 'media_type': 'application/pdf'},
                'caption': [{'plain_text': 'spec.pdf'}],
            },
        }
    ]
    return FakeNotionClient(pages_by_db={}, pages={'page-attach': page}, blocks_by_page={'page-attach': blocks})


def _write_note(
    config: ConfigLayer,
    vault_root: Path,
    relative_path: str,
    *,
    uuid: str,
    area: str,
    note_type: str,
    tags: tuple[str, ...],
    date: str,
    updated: str,
    source: tuple[str, ...],
    source_type: str,
    file_type: str,
    body: str,
) -> Path:
    frontmatter = FrontmatterModel.from_data(
        {
            'uuid': uuid,
            'area': area,
            'type': note_type,
            'tags': list(tags),
            'date': date,
            'updated': updated,
            'source': list(source),
            'source_type': source_type,
            'file_type': file_type,
        },
        tag_registry=config.tag_registry,
    )
    path = vault_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FrontmatterCodec(config).dumps(MarkdownDocument(frontmatter=frontmatter, body=body)), encoding='utf-8')
    return path


def _load_json_fixture(name: str) -> dict[str, Any]:
    fixture_path = Path(__file__).resolve().parents[1] / 'converters' / 'fixtures' / name
    return cast(dict[str, Any], json.loads(fixture_path.read_text(encoding='utf-8')))
