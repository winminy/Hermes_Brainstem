from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from plugins.memory.hermes_memory.backends.notion import NotionBackend, NotionDatasourceSpec, _require_string
from plugins.memory.hermes_memory.interpreter.notion_sync import _render_body


class SkipEntryError(ValueError):
    """Raised when a source entry is intentionally skipped by policy."""


@dataclass(frozen=True, slots=True)
class SourceChunk:
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class MappedNotionEntry:
    datasource: str
    source_page_id: str
    title: str
    chunks: tuple[SourceChunk, ...]
    tag_candidates: tuple[str, ...]
    area: str
    note_type: str
    date: str
    updated: str
    source: tuple[str, ...]
    source_type: str
    file_type: str
    logical_basename: str
    raw_page: Mapping[str, Any]
    raw_properties: Mapping[str, Any]

    def seed_frontmatter(self, *, uuid: str) -> dict[str, object]:
        return {
            'uuid': uuid,
            'area': self.area,
            'type': self.note_type,
            'tags': list(self.tag_candidates),
            'date': self.date,
            'updated': self.updated,
            'source': list(self.source),
            'source_type': self.source_type,
            'file_type': self.file_type,
        }

    def chunk_payload(self) -> list[dict[str, str]]:
        return [{'kind': chunk.kind, 'text': chunk.text} for chunk in self.chunks]


class SourceMapper:
    def __init__(self, notion_backend: NotionBackend) -> None:
        self._notion_backend = notion_backend

    def map_page(self, datasource: str, page: Mapping[str, Any]) -> MappedNotionEntry:
        spec = self._notion_backend.datasources[datasource]
        if not self._notion_backend._is_included(spec, page):
            raise SkipEntryError(f'entry is outside include policy for datasource {datasource}')
        if self._notion_backend._is_excluded(spec, page):
            raise SkipEntryError(f'entry is excluded by datasource policy for {datasource}')
        entry = self._notion_backend._page_to_vault_entry(spec, page)
        title = _require_string(entry.get('title'), field='title')
        body_seed = _render_body(page, title=title)
        source_page_id = _require_string(entry.get('notion_page_id'), field='notion_page_id')
        raw_properties = page.get('properties', {})
        if not isinstance(raw_properties, Mapping):
            raw_properties = {}
        return MappedNotionEntry(
            datasource=datasource,
            source_page_id=source_page_id,
            title=title,
            chunks=_build_chunks(title=title, body_seed=body_seed, page=page, spec=spec),
            tag_candidates=tuple(str(tag) for tag in entry.get('tags', [])),
            area=_require_string(entry.get('area'), field='area'),
            note_type=_require_string(entry.get('type'), field='type'),
            date=_require_string(entry.get('date'), field='date'),
            updated=_require_string(entry.get('updated'), field='updated'),
            source=tuple(str(item) for item in entry.get('source', [])),
            source_type=str(entry.get('source_type', '')),
            file_type=_require_string(entry.get('file_type'), field='file_type'),
            logical_basename=_safe_basename(title),
            raw_page=page,
            raw_properties=raw_properties,
        )


def _build_chunks(*, title: str, body_seed: str, page: Mapping[str, Any], spec: NotionDatasourceSpec) -> tuple[SourceChunk, ...]:
    chunks: list[SourceChunk] = [
        SourceChunk(kind='title', text=title),
        SourceChunk(kind='datasource', text=f'{spec.name} ({spec.db_id})'),
    ]
    if body_seed.strip():
        chunks.append(SourceChunk(kind='properties', text=body_seed))
    url = page.get('url')
    if isinstance(url, str) and url.strip():
        chunks.append(SourceChunk(kind='source_url', text=url.strip()))
    return tuple(chunks)


def _safe_basename(title: str) -> str:
    candidate = title.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'
