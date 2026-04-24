from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

import pytest

from plugins.memory.hermes_memory.attach import (
    DownloadedAttachment,
    NotionAttachment,
    NotionAttachmentExtractor,
)
from plugins.memory.hermes_memory.attach.pipeline import PersistAttachPipeline
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.clock import FrozenClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec
from plugins.memory.hermes_memory.inbox import InboxProcessResult, InboxSourceEntry


class MockAttachmentDownloader:
    def __init__(self, payloads: Mapping[str, DownloadedAttachment]) -> None:
        self._payloads = dict(payloads)
        self.calls: list[str] = []

    def download(self, attachment: NotionAttachment) -> DownloadedAttachment:
        self.calls.append(attachment.attachment_id)
        return self._payloads[attachment.attachment_id]


class RecordingInboxRunner:
    def __init__(self, *, final_area: str = 'knowledge') -> None:
        self.final_area = final_area
        self.calls: list[dict[str, object]] = []

    def ingest(self, entry: InboxSourceEntry, *, vault_root: Path, dry_run: bool = False) -> InboxProcessResult:
        self.calls.append({'entry': entry, 'vault_root': vault_root, 'dry_run': dry_run})
        relative_note = f'{self.final_area}/{entry.title}.md'
        if self.final_area == 'knowledge':
            return InboxProcessResult(
                status='written',
                inbox_path=None if not dry_run else str(vault_root / 'inbox' / f'{entry.title}.md'),
                knowledge_path=relative_note,
                quarantine_path=None,
                reason=None,
                reason_tag=None,
                queue_path=None,
            )
        return InboxProcessResult(
            status='written',
            inbox_path=str(vault_root / 'inbox' / f'{entry.title}.md'),
            knowledge_path=None,
            quarantine_path=None,
            reason=None,
            reason_tag=None,
            queue_path=None,
        )


class FakeBlocksChildren:
    def __init__(self, blocks: Sequence[Mapping[str, object]]) -> None:
        self._blocks = [dict(block) for block in blocks]

    def list(self, *, block_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        del block_id, page_size, start_cursor
        return {'results': list(self._blocks), 'has_more': False, 'next_cursor': None}


class FakeBlocks:
    def __init__(self, blocks: Sequence[Mapping[str, object]]) -> None:
        self.children = FakeBlocksChildren(blocks)


class FakePages:
    def __init__(self, page: Mapping[str, object]) -> None:
        self._page = dict(page)

    def retrieve(self, *, page_id: str) -> dict[str, object]:
        if page_id != self._page['id']:
            raise AssertionError(page_id)
        return dict(self._page)


class FakeDataSources:
    def query(self, *, data_source_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        del data_source_id, page_size, start_cursor
        return {'results': [], 'has_more': False, 'next_cursor': None}


class FakeNotionClient:
    def __init__(self, *, page: Mapping[str, object], blocks: Sequence[Mapping[str, object]]) -> None:
        self.pages = FakePages(page)
        self.blocks = FakeBlocks(blocks)
        self.data_sources = FakeDataSources()


def test_extractor_reads_page_property_files_and_blocks() -> None:
    extractor = NotionAttachmentExtractor()
    attachments = extractor.extract(
        datasource='User Info DB',
        page=_sample_page(),
        blocks=_sample_blocks(),
    )

    assert [item.attachment_id for item in attachments] == [
        'property:첨부:0',
        'block-image-1',
        'block-pdf-1',
    ]
    assert attachments[0].filename == 'notes.md'
    assert attachments[1].is_image is True
    assert attachments[2].extension == 'pdf'


def test_knowledge_binary_writes_raw_attachment_and_routes_companion_note_through_inbox(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runner = RecordingInboxRunner()
    downloader = MockAttachmentDownloader({'block-image-1': DownloadedAttachment(payload=b'png-bytes', media_type='image/png')})
    pipeline = PersistAttachPipeline(config=config, downloader=downloader, inbox_runner=runner, clock=_clock())
    attachment = _sample_blocks_attachment()

    result = pipeline.persist_attachment(attachment, vault_root=tmp_path)

    raw_path = tmp_path / 'attachments' / '2026' / '04' / 'diagram.png'
    manifest_path = raw_path.with_suffix('.png.attach.json')
    assert result.raw_path == 'attachments/2026/04/diagram.png'
    assert raw_path.read_bytes() == b'png-bytes'
    assert manifest_path.exists()
    assert result.note_path == 'knowledge/Project Atlas - diagram.md'
    assert runner.calls and isinstance(runner.calls[0]['entry'], InboxSourceEntry)
    entry = runner.calls[0]['entry']
    assert isinstance(entry, InboxSourceEntry)
    assert entry.file_type == 'png'
    assert entry.source[0].startswith('attach:notion:page-1:block-image-1:')
    assert '![[diagram.png]]' in entry.body
    assert 'raw=attachments/2026/04/diagram.png' in result.saved_path_message


def test_knowledge_markdown_routes_only_through_inbox(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runner = RecordingInboxRunner()
    downloader = MockAttachmentDownloader(
        {'property:첨부:0': DownloadedAttachment(payload=b'# Notes\n\n## Summary\n- item\n', media_type='text/markdown')}
    )
    pipeline = PersistAttachPipeline(config=config, downloader=downloader, inbox_runner=runner, clock=_clock())
    attachment = _sample_property_attachment()

    result = pipeline.persist_attachment(attachment, vault_root=tmp_path)

    assert result.raw_path is None
    assert result.note_path == 'knowledge/Project Atlas - notes.md'
    assert not (tmp_path / 'attachments').exists()
    entry = runner.calls[0]['entry']
    assert isinstance(entry, InboxSourceEntry)
    assert entry.file_type == 'md'
    assert '## Attachment metadata' in entry.body
    assert '- sha256:' in entry.body


def test_skill_binary_writes_directly_to_registered_references_root(tmp_path: Path) -> None:
    config = _config(tmp_path)
    codec = FrontmatterCodec(config)
    downloader = MockAttachmentDownloader({'block-pdf-1': DownloadedAttachment(payload=b'%PDF-1.7', media_type='application/pdf')})
    pipeline = PersistAttachPipeline(config=config, downloader=downloader, clock=_clock())
    attachment = _sample_pdf_attachment()

    result = pipeline.persist_attachment(attachment, scope='skill', skill_name='persist_attach')

    raw_path = config.skill_root() / 'persist_attach' / 'references' / 'spec.pdf'
    note_path = config.skill_root() / 'persist_attach' / 'references' / 'Project Atlas - spec.md'
    assert result.raw_path == str(raw_path)
    assert result.note_path == str(note_path)
    assert raw_path.exists()
    document = codec.loads(note_path.read_text(encoding='utf-8'))
    assert document.frontmatter.area.value == 'knowledge'
    assert document.frontmatter.file_type == 'pdf'
    assert document.frontmatter.source[0].startswith('attach:notion:page-1:block-pdf-1:')
    assert '![[spec.pdf]]' in document.body


def test_skill_markdown_writes_frontmatter_note_directly(tmp_path: Path) -> None:
    config = _config(tmp_path)
    codec = FrontmatterCodec(config)
    downloader = MockAttachmentDownloader(
        {'property:첨부:0': DownloadedAttachment(payload=b'# Notes\n\n## Summary\n- item\n', media_type='text/markdown')}
    )
    pipeline = PersistAttachPipeline(config=config, downloader=downloader, clock=_clock())
    attachment = _sample_property_attachment()

    result = pipeline.persist_attachment(attachment, scope='skill', skill_name='persist_attach')

    note_path = config.skill_root() / 'persist_attach' / 'references' / 'notes.md'
    assert result.note_path == str(note_path)
    document = codec.loads(note_path.read_text(encoding='utf-8'))
    assert document.frontmatter.file_type == 'md'
    assert '## Attachment metadata' in document.body
    assert '# Notes' in document.body
    assert not (config.skill_root() / 'persist_attach' / 'references' / 'notes-1.md').exists()


def test_hash_dedup_reuses_existing_skill_binary_and_note(tmp_path: Path) -> None:
    config = _config(tmp_path)
    downloader = MockAttachmentDownloader({'block-pdf-1': DownloadedAttachment(payload=b'same-bytes', media_type='application/pdf')})
    pipeline = PersistAttachPipeline(config=config, downloader=downloader, clock=_clock())
    attachment = _sample_pdf_attachment()

    first = pipeline.persist_attachment(attachment, scope='skill', skill_name='persist_attach')
    second = pipeline.persist_attachment(attachment, scope='skill', skill_name='persist_attach')

    assert first.raw_path == second.raw_path
    assert first.note_path == second.note_path
    assert second.status == 'deduplicated'
    assert len(list((config.skill_root() / 'persist_attach' / 'references').glob('*.pdf'))) == 1
    assert len(list((config.skill_root() / 'persist_attach' / 'references').glob('*.md'))) == 1


def test_process_notion_page_loads_page_and_blocks_from_notion_backend(tmp_path: Path) -> None:
    config = _config(tmp_path)
    page = _sample_page()
    blocks = _sample_blocks()
    client = FakeNotionClient(page=page, blocks=blocks)
    from plugins.memory.hermes_memory.backends.notion import NotionBackend

    notion_backend = NotionBackend(config=config, client=client)
    downloader = MockAttachmentDownloader(
        {
            'property:첨부:0': DownloadedAttachment(payload=b'# Notes\n', media_type='text/markdown'),
            'block-image-1': DownloadedAttachment(payload=b'img', media_type='image/png'),
            'block-pdf-1': DownloadedAttachment(payload=b'pdf', media_type='application/pdf'),
        }
    )
    runner = RecordingInboxRunner()
    pipeline = PersistAttachPipeline(
        config=config,
        downloader=downloader,
        notion_backend=notion_backend,
        inbox_runner=runner,
        clock=_clock(),
    )

    batch = pipeline.process_notion_page('User Info DB', page_id='page-1', vault_root=tmp_path)

    assert len(batch.results) == 3
    assert [item.attachment_id for item in batch.results] == ['property:첨부:0', 'block-image-1', 'block-pdf-1']
    assert downloader.calls == ['property:첨부:0', 'block-image-1', 'block-pdf-1']
    assert len(runner.calls) == 3


def test_skill_scope_requires_registered_skill_name(tmp_path: Path) -> None:
    config = _config(tmp_path)
    downloader = MockAttachmentDownloader({'block-pdf-1': DownloadedAttachment(payload=b'pdf', media_type='application/pdf')})
    pipeline = PersistAttachPipeline(config=config, downloader=downloader, clock=_clock())

    with pytest.raises(ValueError, match='skill_name is not registered'):
        pipeline.persist_attachment(_sample_pdf_attachment(), scope='skill', skill_name='unknown-skill')


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', log_level='INFO')
    return ConfigLayer.from_settings(settings)


def _clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc))


def _sample_page() -> dict[str, object]:
    return {
        'id': 'page-1',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': 'Project Atlas'}]},
            '첨부': {
                'type': 'files',
                'files': [
                    {
                        'name': 'notes.md',
                        'type': 'file',
                        'file': {'url': 'https://example.test/files/notes.md', 'media_type': 'text/markdown'},
                    }
                ],
            },
        },
    }


def _sample_blocks() -> list[dict[str, object]]:
    return [
        {
            'id': 'block-image-1',
            'type': 'image',
            'image': {
                'type': 'file',
                'file': {'url': 'https://example.test/files/diagram.png', 'media_type': 'image/png'},
                'caption': [{'plain_text': 'diagram.png'}],
            },
        },
        {
            'id': 'block-pdf-1',
            'type': 'pdf',
            'pdf': {
                'type': 'file',
                'file': {'url': 'https://example.test/files/spec.pdf', 'media_type': 'application/pdf'},
                'caption': [{'plain_text': 'spec.pdf'}],
            },
        },
    ]


def _sample_blocks_attachment() -> NotionAttachment:
    return NotionAttachmentExtractor().extract(
        datasource='User Info DB',
        page=_sample_page(),
        blocks=_sample_blocks(),
    )[1]


def _sample_pdf_attachment() -> NotionAttachment:
    return NotionAttachmentExtractor().extract(
        datasource='User Info DB',
        page=_sample_page(),
        blocks=_sample_blocks(),
    )[2]


def _sample_property_attachment() -> NotionAttachment:
    return NotionAttachmentExtractor().extract(
        datasource='User Info DB',
        page=_sample_page(),
        blocks=_sample_blocks(),
    )[0]
