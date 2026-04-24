from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from plugins.memory.hermes_memory.backends.lightrag import LightRAGDocument
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate
from plugins.memory.hermes_memory.backends.llm import StructuredLLMRequest
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.clock import FrozenClock
from plugins.memory.hermes_memory.pipeline import PersistProcessPipeline
from plugins.memory.hermes_memory.pipeline.commit import PipelineCommitter
from plugins.memory.hermes_memory.pipeline.dispatcher import PipelineDispatcher
from plugins.memory.hermes_memory.pipeline.reduce import StructuredEntryReducer


class FakeDataSources:
    def __init__(self, pages_by_db: Mapping[str, list[dict[str, object]]]) -> None:
        self._pages_by_db = {key: list(value) for key, value in pages_by_db.items()}

    def query(self, *, data_source_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        del page_size, start_cursor
        return {
            'results': list(self._pages_by_db.get(data_source_id, [])),
            'has_more': False,
            'next_cursor': None,
        }


class FakePages:
    def retrieve(self, *, page_id: str) -> dict[str, object]:
        if page_id != 'proj-1':
            raise AssertionError(page_id)
        return {
            'id': 'proj-1',
            'properties': {
                'Name': {'type': 'title', 'title': [{'plain_text': 'brainstemV2아키텍쳐수정'}]},
            },
        }


class FakeNotionClient:
    def __init__(self, pages_by_db: Mapping[str, list[dict[str, object]]]) -> None:
        self.data_sources = FakeDataSources(pages_by_db)
        self.pages = FakePages()


class MockStructuredLLM:
    def __init__(self, *, fail_ids: set[str] | None = None) -> None:
        self.fail_ids = fail_ids or set()
        self.requests: list[StructuredLLMRequest] = []

    def generate(self, request: StructuredLLMRequest) -> Mapping[str, object]:
        self.requests.append(request)
        payload = json.loads(request.user_prompt.split('PAYLOAD:\n', 1)[1])
        source_page_id = payload['source_page_id']
        if source_page_id in self.fail_ids:
            raise RuntimeError(f'synthetic reduce failure for {source_page_id}')
        title_hint = str(payload['title_hint'])
        frontmatter = dict(payload['seed_frontmatter'])
        return {
            'title': title_hint,
            'body': f'# {title_hint}\n\n## Summary\n- source_page_id: {source_page_id}',
            'frontmatter': frontmatter,
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
    def __init__(self) -> None:
        self.upserts: list[list[LightRAGDocument]] = []

    def upsert(self, documents: Sequence[LightRAGDocument]) -> Mapping[str, object]:
        batch = list(documents)
        self.upserts.append(batch)
        return {'status': 'success', 'count': len(batch)}

    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        del text, top_k
        return []

    def delete(self, document_ids: Sequence[str]) -> Mapping[str, object]:
        del document_ids
        return {'status': 'deleted'}


def test_full_sync_happy_path_writes_three_files_and_is_idempotent(tmp_path: Path) -> None:
    pipeline, _, embedding_backend, lightrag_backend = _build_pipeline(tmp_path)

    first = pipeline.full_sync(vault_root=tmp_path)
    second = pipeline.full_sync(vault_root=tmp_path)

    knowledge_files = sorted((tmp_path / 'knowledge').glob('*.md'))
    assert len(knowledge_files) == 3
    assert first.counts == {'written': 3}
    assert second.counts == {'unchanged': 3}
    assert len(lightrag_backend.upserts) == 3
    assert len(embedding_backend.calls) == 6
    assert any('brainstemV2아키텍쳐수정' in file.read_text(encoding='utf-8') for file in knowledge_files)


def test_failure_quarantines_one_entry_and_processes_the_rest(tmp_path: Path) -> None:
    pipeline, _, embedding_backend, lightrag_backend = _build_pipeline(tmp_path, fail_ids={'page-2'})

    result = pipeline.full_sync(vault_root=tmp_path)

    knowledge_files = sorted((tmp_path / 'knowledge').glob('*.md'))
    quarantine_files = sorted((tmp_path / '_quarantine').rglob('*'))
    assert len(knowledge_files) == 2
    assert result.counts == {'quarantined': 1, 'written': 2}
    assert len(lightrag_backend.upserts) == 2
    assert len(embedding_backend.calls) == 2
    assert any(path.suffix == '.json' for path in quarantine_files)
    assert any(path.suffix == '.txt' for path in quarantine_files)


def test_dry_run_returns_transforms_without_creating_files(tmp_path: Path) -> None:
    pipeline, _, embedding_backend, lightrag_backend = _build_pipeline(tmp_path)

    result = pipeline.full_sync(vault_root=tmp_path, dry_run=True)

    assert result.counts == {'dry-run': 3}
    assert not (tmp_path / 'knowledge').exists()
    assert not (tmp_path / 'inbox').exists()
    assert not (tmp_path / '_quarantine').exists()
    assert embedding_backend.calls == []
    assert lightrag_backend.upserts == []
    assert all(entry.markdown is not None for entry in result.entries)


def test_incremental_sync_only_processes_changed_entries(tmp_path: Path) -> None:
    pages = _sample_pages()
    pipeline, client, _, lightrag_backend = _build_pipeline(tmp_path, pages=pages)

    initial = pipeline.full_sync(vault_root=tmp_path)
    assert initial.counts == {'written': 3}

    updated_pages = _sample_pages()
    updated_pages['${USER_INFO_DB_ID}'][0]['last_edited_time'] = '2026-04-25T10:00:00.000Z'
    client.data_sources = FakeDataSources(updated_pages)

    incremental = pipeline.incremental_sync(vault_root=tmp_path)

    assert incremental.counts == {'skipped': 2, 'updated': 1}
    assert len(lightrag_backend.upserts) == 4


def test_single_entry_processing_writes_one_note(tmp_path: Path) -> None:
    pipeline, _, _, lightrag_backend = _build_pipeline(tmp_path)

    result = pipeline.process_single_entry('User Info DB', page_id='page-3', vault_root=tmp_path)

    assert result.status == 'written'
    assert result.relative_path == 'knowledge/사용자 기본 정보.md'
    assert len(lightrag_backend.upserts) == 1
    assert (tmp_path / 'knowledge' / '사용자 기본 정보.md').exists()


def _build_pipeline(
    vault_root: Path,
    *,
    pages: Mapping[str, list[dict[str, object]]] | None = None,
    fail_ids: set[str] | None = None,
) -> tuple[PersistProcessPipeline, FakeNotionClient, DummyEmbeddingBackend, RecordingLightRAGBackend]:
    frozen = FrozenClock(datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc))
    settings = HermesMemorySettings(vault_root=vault_root, log_level='INFO')
    config = ConfigLayer.from_settings(settings)
    page_map = pages or _sample_pages()
    client = FakeNotionClient(page_map)
    notion_backend = NotionBackend(config=config, client=client)
    embedding_backend = DummyEmbeddingBackend()
    lightrag_backend = RecordingLightRAGBackend()
    reducer = StructuredEntryReducer(config=config, llm_backend=MockStructuredLLM(fail_ids=fail_ids), clock=frozen)
    committer = PipelineCommitter(config=config, lightrag_backend=lightrag_backend, clock=frozen)
    pipeline = PersistProcessPipeline(
        config=config,
        notion_backend=notion_backend,
        reducer=reducer,
        embedding_backend=embedding_backend,
        lightrag_backend=lightrag_backend,
        dispatcher=PipelineDispatcher(config),
        committer=committer,
        clock=frozen,
    )
    return pipeline, client, embedding_backend, lightrag_backend


def _sample_pages() -> dict[str, list[dict[str, object]]]:
    return {
        '${SUB_TASK_DB_ID}': [
            _page('page-1', '프로젝트 메모', '메모/ 리소스', relation_ids=['proj-1']),
            _page('page-2', '백로그 정리', 'Project Backlogs'),
        ],
        '${USER_INFO_DB_ID}': [
            _page('page-3', '사용자 기본 정보', '기본 정보'),
        ],
    }


def _page(
    page_id: str,
    title: str,
    notion_type: str,
    *,
    relation_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        'id': page_id,
        'url': f'https://www.notion.so/{page_id}',
        'created_time': '2026-04-23T08:35:00.000Z',
        'last_edited_time': '2026-04-24T09:00:00.000Z',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': title}]},
            '유형': {'type': 'select', 'select': {'name': notion_type}},
            '프로젝트': {'type': 'relation', 'relation': [{'id': relation_id} for relation_id in relation_ids or []]},
        },
    }
