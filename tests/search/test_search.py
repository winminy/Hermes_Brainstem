from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate
from plugins.memory.hermes_memory.search import SearchFilters, direct_search, read, semantic_search


class RecordingLightRAGBackend:
    def __init__(self, candidates: Sequence[LightRAGCandidate]) -> None:
        self._candidates = tuple(candidates)
        self.calls: list[tuple[str, int]] = []

    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        self.calls.append((text, top_k))
        return self._candidates


class DownLightRAGBackend:
    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        del text, top_k
        raise RuntimeError('LightRAG is down')


def test_semantic_search_uses_lightrag_then_supplements_with_direct_file_matches(tmp_path: Path) -> None:
    config = _config(tmp_path)
    alpha = _write_note(
        config,
        tmp_path,
        'knowledge/Alpha.md',
        uuid='obs:20260424T0500-1',
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
        uuid='obs:20260424T0500-2',
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
    hidden = _write_note(
        config,
        tmp_path,
        '_quarantine/2026-04/Hidden.md',
        uuid='obs:20260424T0500-8',
        area='knowledge',
        note_type='memo',
        tags=('AI',),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:hidden',),
        source_type='',
        file_type='md',
        body='# Hidden\n\nThis quarantined note must never be returned by search.',
    )
    backend = RecordingLightRAGBackend(
        [
            LightRAGCandidate(title='Hidden', path=hidden.as_posix(), score=0.99, type='memo'),
            LightRAGCandidate(title='Alpha', path=alpha.as_posix(), score=0.93, type='knowledge'),
        ]
    )

    hits = semantic_search('semantic search', backend, config=config, vault_root=tmp_path, top_k=2)

    assert [hit.metadata.title for hit in hits] == ['Alpha', 'Beta']
    assert all(hit.metadata.title != 'Hidden' for hit in hits)
    assert hits[0].origin == 'semantic'
    assert hits[0].score == pytest.approx(0.93)
    assert 'Semantic vector search' in hits[0].snippet
    assert hits[1].origin == 'direct_file'
    assert backend.calls == [('semantic search', 6)]


def test_semantic_search_gracefully_degrades_to_vault_search_when_lightrag_is_down(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config(tmp_path)
    _write_note(
        config,
        tmp_path,
        'knowledge/Fallback.md',
        uuid='obs:20260424T0500-3',
        area='knowledge',
        note_type='memo',
        tags=('AI', 'PKM'),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:fallback',),
        source_type='',
        file_type='md',
        body='# Fallback\n\nDirect vault search still answers when semantic indexing is unavailable.',
    )

    with caplog.at_level('WARNING'):
        hits = semantic_search('semantic indexing', DownLightRAGBackend(), config=config, vault_root=tmp_path, top_k=3)

    assert [hit.metadata.title for hit in hits] == ['Fallback']
    assert all(hit.origin == 'direct_file' for hit in hits)
    assert any('semantic.search.lightrag_unavailable' in message for message in caplog.messages)


def test_direct_file_search_applies_frontmatter_filter_combinations(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_note(
        config,
        tmp_path,
        'knowledge/Alpha.md',
        uuid='obs:20260424T0500-4',
        area='knowledge',
        note_type='knowledge',
        tags=('AI', '개발'),
        date='2026-04-23',
        updated='2026-04-23',
        source=('session:alpha-filter',),
        source_type='',
        file_type='md',
        body='# Alpha\n\nRetention policy memo for semantic search.',
    )
    _write_note(
        config,
        tmp_path,
        'knowledge/Beta.md',
        uuid='obs:20260424T0500-5',
        area='knowledge',
        note_type='memo',
        tags=('AI', 'PKM'),
        date='2026-04-24',
        updated='2026-04-24',
        source=('notion:beta-filter',),
        source_type='notion',
        file_type='md',
        body='# Beta\n\nRetention policy memo for semantic search.',
    )
    _write_note(
        config,
        tmp_path,
        'inbox/Gamma.md',
        uuid='obs:20260424T0500-6',
        area='inbox',
        note_type='memo',
        tags=('AI', 'PKM'),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:gamma-filter',),
        source_type='',
        file_type='md',
        body='# Gamma\n\nRetention policy memo for semantic search.',
    )

    hits = direct_search(
        'retention policy',
        config=config,
        vault_root=tmp_path,
        filters=SearchFilters(
            area='knowledge',
            type='memo',
            tags=('AI', 'PKM'),
            date_from='2026-04-24',
            date_to='2026-04-24',
            source_type='notion',
        ),
        top_k=5,
    )

    assert [hit.metadata.title for hit in hits] == ['Beta']
    assert hits[0].metadata.area == 'knowledge'
    assert hits[0].metadata.type == 'memo'
    assert hits[0].metadata.tags == ('AI', 'PKM')
    assert hits[0].metadata.date == '2026-04-24'
    assert hits[0].metadata.source_type == 'notion'


def test_direct_file_search_supports_tag_match_mode_all_and_any(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_note(
        config,
        tmp_path,
        'knowledge/Alpha.md',
        uuid='obs:20260424T0500-9',
        area='knowledge',
        note_type='memo',
        tags=('AI', '개발'),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:alpha-tag-mode',),
        source_type='',
        file_type='md',
        body='# Alpha\n\nTag mode testing keeps search behavior explicit.',
    )
    _write_note(
        config,
        tmp_path,
        'knowledge/Beta.md',
        uuid='obs:20260424T0500-10',
        area='knowledge',
        note_type='memo',
        tags=('AI', 'PKM'),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:beta-tag-mode',),
        source_type='',
        file_type='md',
        body='# Beta\n\nTag mode testing keeps search behavior explicit.',
    )

    all_hits = direct_search(
        'tag mode testing',
        config=config,
        vault_root=tmp_path,
        filters=SearchFilters(area='knowledge', tags=('AI', 'PKM'), tag_match_mode='all'),
        top_k=5,
    )
    any_hits = direct_search(
        'tag mode testing',
        config=config,
        vault_root=tmp_path,
        filters=SearchFilters(area='knowledge', tags=('개발', 'PKM'), tag_match_mode='any'),
        top_k=5,
    )

    assert [hit.metadata.title for hit in all_hits] == ['Beta']
    assert [hit.metadata.title for hit in any_hits] == ['Alpha', 'Beta']


def test_direct_file_read_blocks_vault_escape_and_returns_frontmatter_with_body(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_note(
        config,
        tmp_path,
        'knowledge/Reader.md',
        uuid='obs:20260424T0500-7',
        area='knowledge',
        note_type='knowledge',
        tags=('AI',),
        date='2026-04-24',
        updated='2026-04-24',
        source=('session:reader',),
        source_type='',
        file_type='md',
        body='# Reader\n\nBody snippet for direct read.',
    )

    entry = read('knowledge/Reader.md', config=config, vault_root=tmp_path)

    assert entry.frontmatter.uuid == 'obs:20260424T0500-7'
    assert 'Body snippet for direct read.' in entry.body
    with pytest.raises(ValueError, match='cannot escape the vault root'):
        read('../outside.md', config=config, vault_root=tmp_path)


def _config(tmp_path: Path) -> ConfigLayer:
    return ConfigLayer.from_settings(HermesMemorySettings(vault_root=tmp_path, log_level='INFO'))


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
    codec = FrontmatterCodec(config)
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
    path.write_text(codec.dumps(MarkdownDocument(frontmatter=frontmatter, body=body)), encoding='utf-8')
    return path
