from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json

import httpx

from plugins.memory.hermes_memory.backends.lightrag import LightRAGDocument, LightRAGHTTPBackend
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.clock import FrozenClock
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate
from plugins.memory.hermes_memory.interpreter.notion_sync import NotionInterpreter


class FakeDataSources:
    def query(self, *, data_source_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        if data_source_id == '${SUB_TASK_DB_ID}':
            return {
                'results': [_subtask_page('memo-1', '프로젝트 메모', '메모/ 리소스', relation_ids=['proj-1'])],
                'has_more': False,
                'next_cursor': None,
            }
        raise AssertionError(f'unexpected datasource: {data_source_id}')


class FakePages:
    def retrieve(self, *, page_id: str) -> dict[str, object]:
        if page_id == 'proj-1':
            return {
                'id': page_id,
                'properties': {
                    'Name': {
                        'type': 'title',
                        'title': [{'plain_text': 'brainstemV2아키텍쳐수정'}],
                    }
                },
            }
        raise AssertionError(f'unexpected relation lookup: {page_id}')


class FakeNotionClient:
    def __init__(self) -> None:
        self.data_sources = FakeDataSources()
        self.pages = FakePages()


class DummyEmbeddingBackend:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.25, 0.75] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.25, 0.75]


class RecordingLightRAGBackend:
    def __init__(self) -> None:
        self.documents: list[LightRAGDocument] = []

    def upsert(self, documents: Sequence[LightRAGDocument]) -> Mapping[str, object]:
        self.documents = list(documents)
        return {'status': 'success', 'count': len(documents)}

    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        raise AssertionError('query_related is not used in this test')

    def delete(self, document_ids: Sequence[str]) -> Mapping[str, object]:
        raise AssertionError('delete is not used in this test')


def test_notion_interpreter_builds_entry_embedding_and_lightrag_upsert() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings())
    embedding_backend = DummyEmbeddingBackend()
    lightrag_backend = RecordingLightRAGBackend()
    interpreter = NotionInterpreter(
        config=config,
        notion_backend=NotionBackend(config=config, client=FakeNotionClient()),
        embedding_backend=embedding_backend,
        lightrag_backend=lightrag_backend,
        clock=FrozenClock(datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)),
    )

    result = interpreter.sync_datasource('Sub-task DB')

    assert result.lightrag_response == {'status': 'success', 'count': 1}
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.title == '프로젝트 메모'
    assert entry.logical_path == 'knowledge/프로젝트 메모.md'
    assert entry.frontmatter.type.value == 'memo'
    assert entry.frontmatter.tags == ('brainstemV2아키텍쳐수정',)
    assert entry.tag_hierarchy[0].parent_path == ('project',)
    assert embedding_backend.calls and embedding_backend.calls[0][0].startswith('---\nuuid: obs:20260423T1200')
    assert lightrag_backend.documents[0].embedding == (0.25, 0.75)
    assert lightrag_backend.documents[0].metadata['file_source'] == 'knowledge/프로젝트 메모.md'


def test_lightrag_http_backend_uses_official_docs_payload_defaults() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings())
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode('utf-8'))
        requests.append((request.method, request.url.path, payload))
        if request.url.path == '/documents/texts':
            return httpx.Response(200, json={'status': 'success'})
        if request.url.path == '/query':
            return httpx.Response(
                200,
                json={
                    'response': 'ok',
                    'references': [
                        {'reference_id': 'ref-1', 'file_path': 'knowledge/프로젝트 메모.md'},
                    ],
                },
            )
        if request.url.path == '/documents/delete_document':
            return httpx.Response(200, json={'status': 'deleted'})
        raise AssertionError(request.url.path)

    client = httpx.Client(base_url=config.settings.lightrag.base_url, transport=httpx.MockTransport(handler))
    backend = LightRAGHTTPBackend(config=config, embedding_backend=DummyEmbeddingBackend(), client=client)

    assert backend.upsert([
        LightRAGDocument(
            id='obs:20260423T1200',
            text='markdown',
            metadata={'path': 'knowledge/프로젝트 메모.md'},
            embedding=(0.25, 0.75),
        )
    ]) == {'status': 'success'}
    candidates = backend.query_related('프로젝트', top_k=3)
    assert backend.delete(['obs:20260423T1200']) == {'status': 'deleted'}

    assert requests[0] == (
        'POST',
        '/documents/texts',
        {'texts': ['markdown'], 'file_sources': ['knowledge/프로젝트 메모.md']},
    )
    assert requests[1][0:2] == ('POST', '/query')
    assert requests[2] == ('DELETE', '/documents/delete_document', {'doc_ids': ['obs:20260423T1200']})
    assert candidates[0].path == 'knowledge/프로젝트 메모.md'
    assert candidates[0].type == 'knowledge'


def _subtask_page(page_id: str, title: str, notion_type: str, *, relation_ids: list[str] | None = None) -> dict[str, object]:
    relation_payload = [{'id': relation_id} for relation_id in relation_ids or []]
    return {
        'id': page_id,
        'url': f'https://www.notion.so/{page_id}',
        'created_time': '2026-04-23T08:35:00.000Z',
        'last_edited_time': '2026-04-24T09:00:00.000Z',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': title}]},
            '유형': {'type': 'select', 'select': {'name': notion_type}},
            '프로젝트': {'type': 'relation', 'relation': relation_payload},
        },
    }
