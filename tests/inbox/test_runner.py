from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path

from plugins.memory.hermes_memory.backends.lightrag import LightRAGDocument
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.clock import FrozenClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate
from plugins.memory.hermes_memory.inbox import (
    DedupDecision,
    GraduationResult,
    InboxClassification,
    InboxDeduplicator,
    InboxGraduator,
    InboxRunner,
    InboxSourceEntry,
)
from plugins.memory.hermes_memory.pipeline import PersistProcessPipeline, SyncEntryResult


class EmptyDataSources:
    def query(self, *, data_source_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        del data_source_id, page_size, start_cursor
        return {'results': [], 'has_more': False, 'next_cursor': None}


class EmptyPages:
    def retrieve(self, *, page_id: str) -> dict[str, object]:
        raise AssertionError(page_id)

    def update(self, *, page_id: str, properties: Mapping[str, object]) -> dict[str, object]:
        return {'id': page_id, 'properties': dict(properties)}


class EmptyBlockChildren:
    def append(self, *, block_id: str, children: Sequence[Mapping[str, object]]) -> dict[str, object]:
        return {'block_id': block_id, 'children': list(children)}


class EmptyBlocks:
    def __init__(self) -> None:
        self.children = EmptyBlockChildren()


class EmptyNotionClient:
    def __init__(self) -> None:
        self.data_sources = EmptyDataSources()
        self.pages = EmptyPages()
        self.blocks = EmptyBlocks()


class DummyEmbeddingBackend:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        del text
        return [0.1, 0.2, 0.3]


class RecordingLightRAGBackend:
    def __init__(self, *, candidates: Sequence[LightRAGCandidate] = ()) -> None:
        self.candidates = list(candidates)
        self.upserts: list[list[LightRAGDocument]] = []

    def upsert(self, documents: Sequence[LightRAGDocument]) -> Mapping[str, object]:
        batch = list(documents)
        self.upserts.append(batch)
        return {'status': 'success', 'count': len(batch)}

    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        del text, top_k
        return list(self.candidates)

    def delete(self, document_ids: Sequence[str]) -> Mapping[str, object]:
        del document_ids
        return {'status': 'deleted'}


class StaticClassifier:
    def __init__(self, by_title: Mapping[str, InboxClassification]) -> None:
        self.by_title = dict(by_title)

    def classify(self, *, title: str, document: object) -> InboxClassification:
        del document
        return self.by_title[title]


class RecordingPipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def process_single_entry(
        self,
        datasource: str,
        *,
        page: Mapping[str, object] | None = None,
        page_id: str | None = None,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> SyncEntryResult:
        del page
        self.calls.append(
            {
                'datasource': datasource,
                'page_id': page_id,
                'vault_root': vault_root,
                'dry_run': dry_run,
            }
        )
        return SyncEntryResult(
            datasource=datasource,
            source_page_id=page_id or 'unknown',
            status='written',
            relative_path='knowledge/notion-processed.md',
            reason=None,
            quarantine_path=None,
            markdown='# notion processed',
        )


class RecordingPageWriter:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    def retrieve(self, *, page_id: str) -> dict[str, object]:
        raise AssertionError(page_id)

    def update(self, *, page_id: str, properties: Mapping[str, object]) -> dict[str, object]:
        payload: dict[str, object] = {'page_id': page_id, 'properties': dict(properties)}
        self.updates.append(payload)
        return payload


class RecordingBlockChildren:
    def __init__(self) -> None:
        self.appends: list[dict[str, object]] = []

    def append(self, *, block_id: str, children: Sequence[Mapping[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {'block_id': block_id, 'children': [dict(child) for child in children]}
        self.appends.append(payload)
        return payload


class RecordingBlocks:
    def __init__(self) -> None:
        self.children = RecordingBlockChildren()


class RecordingNotionWriteClient:
    def __init__(self) -> None:
        self.data_sources = EmptyDataSources()
        self.pages = RecordingPageWriter()
        self.blocks = RecordingBlocks()


def test_happy_path_graduates_to_knowledge_and_upserts_lightrag(tmp_path: Path) -> None:
    runner, lightrag = _build_runner(
        tmp_path,
        classifications={
            'Inbox Happy': InboxClassification(
                status='success',
                title='Graduated Note',
                body='# Graduated Note\n\n## Summary\n- done',
                area='knowledge',
                note_type='knowledge',
                tags=('PKM',),
                reason=None,
                reason_tag=None,
            )
        },
    )

    result = runner.ingest(
        InboxSourceEntry(title='Inbox Happy', body='# Inbox Happy', source=('session:happy',)),
        vault_root=tmp_path,
    )

    assert result.status == 'written'
    assert result.knowledge_path == 'knowledge/Graduated Note.md'
    assert not (tmp_path / 'inbox' / 'Inbox Happy.md').exists()
    written = tmp_path / 'knowledge' / 'Graduated Note.md'
    assert written.exists()
    assert 'area: knowledge' in written.read_text(encoding='utf-8')
    assert len(lightrag.upserts) == 1
    assert lightrag.upserts[0][0].metadata['path'] == 'knowledge/Graduated Note.md'


def test_ambiguous_classification_stays_in_inbox_with_reason_tag(tmp_path: Path) -> None:
    runner, _ = _build_runner(
        tmp_path,
        classifications={
            'Needs Review': InboxClassification(
                status='ambiguous',
                title='Needs Review',
                body='# Needs Review',
                area=None,
                note_type=None,
                tags=(),
                reason='type inference was ambiguous',
                reason_tag='needs-confirmation',
            )
        },
    )

    result = runner.ingest(
        InboxSourceEntry(title='Needs Review', body='# Needs Review', source=('session:ambiguous',)),
        vault_root=tmp_path,
    )

    inbox_path = tmp_path / 'inbox' / 'Needs Review.md'
    assert result.status == 'ambiguous'
    assert result.inbox_path == str(inbox_path)
    assert inbox_path.exists()
    assert 'reason_tag: needs-confirmation' in inbox_path.read_text(encoding='utf-8')
    state = json.loads(inbox_path.with_suffix('.inbox-state.json').read_text(encoding='utf-8'))
    assert state['reason_tag'] == 'needs-confirmation'
    assert not (tmp_path / 'knowledge').exists()


def test_invalid_classification_moves_note_to_quarantine(tmp_path: Path) -> None:
    runner, _ = _build_runner(
        tmp_path,
        classifications={
            'Broken': InboxClassification(
                status='invalid',
                title='Broken',
                body='# Broken',
                area=None,
                note_type=None,
                tags=(),
                reason='frontmatter contract violation',
                reason_tag='invalid-frontmatter',
            )
        },
    )

    result = runner.ingest(
        InboxSourceEntry(title='Broken', body='# Broken', source=('session:invalid',)),
        vault_root=tmp_path,
    )

    assert result.status == 'quarantined'
    assert result.quarantine_path is not None
    quarantine_path = Path(result.quarantine_path)
    assert quarantine_path.exists()
    assert not (tmp_path / 'inbox' / 'Broken.md').exists()
    assert quarantine_path.with_suffix('.md.reason.txt').exists()


def test_source_idempotency_skips_duplicate_inbox_entry(tmp_path: Path) -> None:
    runner, _ = _build_runner(
        tmp_path,
        classifications={
            'Duplicate': InboxClassification(
                status='success',
                title='Duplicate',
                body='# Duplicate',
                area='knowledge',
                note_type='memo',
                tags=('PKM',),
                reason=None,
                reason_tag=None,
            )
        },
    )
    _seed_note(tmp_path, title='Existing', area='knowledge', uuid='obs:20260423T1200-1', source=('session:dup',))

    result = runner.ingest(
        InboxSourceEntry(title='Duplicate', body='# Duplicate', source=('session:dup',)),
        vault_root=tmp_path,
    )

    assert result.status == 'skipped'
    assert not (tmp_path / 'inbox' / 'Duplicate.md').exists()


def test_uuid_collision_only_updates_updated_field(tmp_path: Path) -> None:
    runner, _ = _build_runner(
        tmp_path,
        classifications={
            'Collision': InboxClassification(
                status='success',
                title='Collision',
                body='# Collision',
                area='knowledge',
                note_type='memo',
                tags=('PKM',),
                reason=None,
                reason_tag=None,
            )
        },
    )
    existing_path = _seed_note(
        tmp_path,
        title='Existing UUID',
        area='knowledge',
        uuid='obs:20260423T1200-1',
        source=('session:old',),
        updated='2026-04-20',
        body='# Existing UUID\n\n## Summary\n- keep me',
    )

    result = runner.ingest(
        InboxSourceEntry(
            title='Collision',
            body='# Collision',
            source=('session:new',),
            uuid='obs:20260423T1200-1',
            updated='2026-04-23',
        ),
        vault_root=tmp_path,
    )

    assert result.status == 'updated-existing'
    assert result.knowledge_path == str(existing_path)
    text = existing_path.read_text(encoding='utf-8')
    assert 'updated: 2026-04-23' in text
    assert '- keep me' in text
    assert not (tmp_path / 'inbox' / 'Collision.md').exists()


def test_similarity_candidates_are_queued_and_note_stays_in_inbox(tmp_path: Path) -> None:
    runner, _ = _build_runner(
        tmp_path,
        classifications={
            'Potential Merge': InboxClassification(
                status='success',
                title='Potential Merge',
                body='# Potential Merge',
                area='knowledge',
                note_type='memo',
                tags=('PKM',),
                reason=None,
                reason_tag=None,
            )
        },
        candidates=[LightRAGCandidate(title='Existing Match', path='knowledge/existing.md', score=0.95, type='knowledge')],
    )

    result = runner.ingest(
        InboxSourceEntry(title='Potential Merge', body='# Potential Merge', source=('session:merge',)),
        vault_root=tmp_path,
    )

    assert result.status == 'queued-merge'
    assert result.queue_path is not None
    queue_path = Path(result.queue_path)
    assert queue_path.exists()
    assert 'Existing Match' in queue_path.read_text(encoding='utf-8')
    assert (tmp_path / 'inbox' / 'Potential Merge.md').exists()


def test_inbox_similarity_candidates_do_not_create_inbox_to_inbox_path(tmp_path: Path) -> None:
    runner, lightrag = _build_runner(
        tmp_path,
        classifications={
            'Inbox Candidate': InboxClassification(
                status='success',
                title='Inbox Candidate Graduated',
                body='# Inbox Candidate Graduated',
                area='knowledge',
                note_type='memo',
                tags=('PKM',),
                reason=None,
                reason_tag=None,
            )
        },
        candidates=[LightRAGCandidate(title='Other Inbox Note', path='inbox/existing.md', score=0.99, type='memo')],
    )

    result = runner.ingest(
        InboxSourceEntry(title='Inbox Candidate', body='# Inbox Candidate', source=('session:no-inbox-route',)),
        vault_root=tmp_path,
    )

    assert result.status == 'written'
    assert result.knowledge_path == 'knowledge/Inbox Candidate Graduated.md'
    assert result.queue_path is None
    assert not (tmp_path / 'inbox' / '.hermes-inbox-merge-queue.jsonl').exists()
    assert not (tmp_path / 'inbox' / 'Inbox Candidate.md').exists()
    assert (tmp_path / 'knowledge' / 'Inbox Candidate Graduated.md').exists()
    assert len(lightrag.upserts) == 1


def test_runner_processes_entries_sequentially(tmp_path: Path) -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings(vault_root=tmp_path, log_level='INFO'))
    active = {'value': False}
    seen: list[str] = []

    class SequentialDeduplicator:
        def deduplicate(self, *, entry_path: Path, document: object, title: str, vault_root: Path, dry_run: bool = False) -> DedupDecision:
            del entry_path, document, vault_root, dry_run
            if active['value']:
                raise AssertionError('deduplicator called concurrently')
            active['value'] = True
            seen.append(f'dedup:{title}')
            return DedupDecision(action='continue')

    class SequentialClassifier:
        def classify(self, *, title: str, document: object) -> InboxClassification:
            del document
            if not active['value']:
                raise AssertionError('classifier ran without a matching dedup step')
            seen.append(f'classify:{title}')
            active['value'] = False
            return InboxClassification(
                status='ambiguous',
                title=title,
                body='# waiting',
                area=None,
                note_type=None,
                tags=(),
                reason='human review',
                reason_tag='needs-confirmation',
            )

    class SequentialGraduator:
        def graduate(self, **kwargs: object) -> GraduationResult:
            raise AssertionError(kwargs)

    runner = InboxRunner(
        config,
        deduplicator=SequentialDeduplicator(),  # type: ignore[arg-type]
        classifier=SequentialClassifier(),  # type: ignore[arg-type]
        graduator=SequentialGraduator(),  # type: ignore[arg-type]
        clock=FrozenClock(datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)),
    )

    results = runner.run(
        [
            InboxSourceEntry(title='one', body='# one', source=('session:1',)),
            InboxSourceEntry(title='two', body='# two', source=('session:2',)),
        ],
        vault_root=tmp_path,
    )

    assert not active['value']
    assert [result.status for result in results] == ['ambiguous', 'ambiguous']
    assert seen == ['dedup:one', 'classify:one', 'dedup:two', 'classify:two']


def test_process_notion_page_delegates_to_pipeline_and_writes_back(tmp_path: Path) -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings(vault_root=tmp_path, log_level='INFO'))
    frozen = FrozenClock(datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc))
    notion_client = RecordingNotionWriteClient()
    notion_backend = NotionBackend(config=config, client=notion_client)
    pipeline = RecordingPipeline()
    lightrag = RecordingLightRAGBackend()
    runner = InboxRunner(
        config,
        deduplicator=InboxDeduplicator(config, lightrag_backend=lightrag, clock=frozen),
        classifier=StaticClassifier({}),  # type: ignore[arg-type]
        graduator=InboxGraduator(
            config,
            pipeline=PersistProcessPipeline(
                config=config,
                notion_backend=notion_backend,
                embedding_backend=DummyEmbeddingBackend(),
                lightrag_backend=lightrag,
                clock=frozen,
            ),
        ),
        notion_backend=notion_backend,
        pipeline=pipeline,  # type: ignore[arg-type]
        clock=frozen,
    )

    result = runner.process_notion_page(
        'User Info DB',
        page_id='page-123',
        vault_root=tmp_path,
        write_back_properties={'Status': {'status': {'name': 'Processed'}}},
        write_back_children=(
            {
                'object': 'block',
                'type': 'paragraph',
                'paragraph': {'rich_text': [{'type': 'text', 'text': {'content': 'Processed by inbox'}}]},
            },
        ),
    )

    assert result.status == 'written'
    assert result.relative_path == 'knowledge/notion-processed.md'
    assert pipeline.calls == [
        {
            'datasource': 'User Info DB',
            'page_id': 'page-123',
            'vault_root': tmp_path,
            'dry_run': False,
        }
    ]
    assert notion_client.pages.updates == [
        {'page_id': 'page-123', 'properties': {'Status': {'status': {'name': 'Processed'}}}}
    ]
    assert notion_client.blocks.children.appends == [
        {
            'block_id': 'page-123',
            'children': [
                {
                    'object': 'block',
                    'type': 'paragraph',
                    'paragraph': {'rich_text': [{'type': 'text', 'text': {'content': 'Processed by inbox'}}]},
                }
            ],
        }
    ]
    assert result.write_back_response == {
        'page': {'page_id': 'page-123', 'properties': {'Status': {'status': {'name': 'Processed'}}}},
        'blocks': {
            'block_id': 'page-123',
            'children': [
                {
                    'object': 'block',
                    'type': 'paragraph',
                    'paragraph': {'rich_text': [{'type': 'text', 'text': {'content': 'Processed by inbox'}}]},
                }
            ],
        },
    }


def _build_runner(
    vault_root: Path,
    *,
    classifications: Mapping[str, InboxClassification],
    candidates: Sequence[LightRAGCandidate] = (),
) -> tuple[InboxRunner, RecordingLightRAGBackend]:
    frozen = FrozenClock(datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc))
    config = ConfigLayer.from_settings(HermesMemorySettings(vault_root=vault_root, log_level='INFO'))
    lightrag = RecordingLightRAGBackend(candidates=candidates)
    notion_backend = NotionBackend(config=config, client=EmptyNotionClient())
    pipeline = PersistProcessPipeline(
        config=config,
        notion_backend=notion_backend,
        embedding_backend=DummyEmbeddingBackend(),
        lightrag_backend=lightrag,
        clock=frozen,
    )
    runner = InboxRunner(
        config,
        deduplicator=InboxDeduplicator(config, lightrag_backend=lightrag, clock=frozen),
        classifier=StaticClassifier(classifications),  # type: ignore[arg-type]
        graduator=InboxGraduator(config, pipeline=pipeline),
        notion_backend=notion_backend,
        pipeline=pipeline,
        clock=frozen,
    )
    return runner, lightrag


def _seed_note(
    vault_root: Path,
    *,
    title: str,
    area: str,
    uuid: str,
    source: tuple[str, ...],
    updated: str = '2026-04-23',
    body: str | None = None,
) -> Path:
    config = ConfigLayer.from_settings(HermesMemorySettings(vault_root=vault_root, log_level='INFO'))
    codec = FrontmatterCodec(config)
    frontmatter = FrontmatterModel.from_data(
        {
            'uuid': uuid,
            'area': area,
            'type': 'memo',
            'tags': ['PKM'],
            'date': '2026-04-23',
            'updated': updated,
            'source': list(source),
            'source_type': '',
            'file_type': 'md',
        },
        tag_registry=config.tag_registry,
    )
    document = codec.dumps(MarkdownDocument(frontmatter=frontmatter, body=body or f'# {title}'))
    path = vault_root / area / f'{title}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding='utf-8')
    return path
