from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jsonschema import validate

from plugins.memory.hermes_memory.backends.embedding import EmbeddingBackend, build_embedding_backend
from plugins.memory.hermes_memory.backends.lightrag import LightRAGBackend, LightRAGDocument, LightRAGHTTPBackend
from plugins.memory.hermes_memory.backends.notion import (
    NotionBackend,
    _extract_title,
    _iso_date,
    _require_string,
    render_notion_body,
)
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel, TagHierarchy
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator

from .schema_builder import SchemaBuilder


@dataclass(frozen=True, slots=True)
class InterpretedVaultEntry:
    title: str
    logical_path: str
    body: str
    frontmatter: FrontmatterModel
    markdown: str
    embedding: tuple[float, ...]
    tag_hierarchy: tuple[TagHierarchy, ...]
    source_page_id: str
    datasource: str
    raw_properties: Mapping[str, Any]

    def schema_payload(self) -> dict[str, object]:
        return {
            'title': self.title,
            'body': self.body,
            'frontmatter': self.frontmatter.ordered_dump(),
        }

    def to_lightrag_document(self) -> LightRAGDocument:
        return LightRAGDocument(
            id=self.frontmatter.uuid,
            text=self.markdown,
            embedding=self.embedding,
            metadata={
                'path': self.logical_path,
                'file_source': self.logical_path,
                'title': self.title,
                'area': self.frontmatter.area.value,
                'type': self.frontmatter.type.value,
                'tags': list(self.frontmatter.tags),
                'source': list(self.frontmatter.source),
                'tag_hierarchy': [
                    {'tag': item.tag, 'parent_path': list(item.parent_path)}
                    for item in self.tag_hierarchy
                ],
                'notion_page_id': self.source_page_id,
                'datasource': self.datasource,
            },
        )


@dataclass(frozen=True, slots=True)
class NotionSyncResult:
    datasource: str
    entries: tuple[InterpretedVaultEntry, ...]
    lightrag_response: Mapping[str, Any]


class NotionInterpreter:
    def __init__(
        self,
        *,
        config: ConfigLayer,
        notion_backend: NotionBackend | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        lightrag_backend: LightRAGBackend | None = None,
        schema_builder: SchemaBuilder | None = None,
        clock: Clock | None = None,
        uuid_generator: UUIDGenerator | None = None,
    ) -> None:
        self._config = config
        self._notion_backend = notion_backend or NotionBackend(config=config)
        self._embedding_backend = embedding_backend or build_embedding_backend(config)
        self._lightrag_backend = lightrag_backend or LightRAGHTTPBackend(
            config=config,
            embedding_backend=self._embedding_backend,
        )
        self._schema_builder = schema_builder or SchemaBuilder(config)
        self._clock = clock or SystemClock(config.settings.timezone)
        self._uuid_generator = uuid_generator or UUIDGenerator(clock=self._clock)
        self._codec = FrontmatterCodec(config)

    def sync_datasource(self, datasource: str) -> NotionSyncResult:
        entries = self.interpret_datasource(datasource)
        if entries:
            response = self._lightrag_backend.upsert([entry.to_lightrag_document() for entry in entries])
        else:
            response = {'status': 'skipped', 'reason': 'no eligible rows'}
        return NotionSyncResult(datasource=datasource, entries=tuple(entries), lightrag_response=response)

    def interpret_datasource(self, datasource: str) -> list[InterpretedVaultEntry]:
        spec = self._notion_backend.datasources[datasource]
        entries: list[InterpretedVaultEntry] = []
        for page in self._notion_backend.query_datasource(datasource):
            if not self._notion_backend._is_included(spec, page):
                continue
            if self._notion_backend._is_excluded(spec, page):
                continue
            entries.append(self.interpret_page(datasource, page))
        return entries

    def interpret_page(self, datasource: str, page: Mapping[str, Any]) -> InterpretedVaultEntry:
        spec = self._notion_backend.datasources[datasource]
        entry = self._notion_backend._page_to_vault_entry(spec, page)
        title = _extract_title(page)
        source_page_id = _require_string(page.get('id'), field='id')
        validated_tags = self._config.tag_registry.validate(tuple(str(tag) for tag in entry.get('tags', [])))
        created = _iso_date(page.get('created_time'))
        updated = _iso_date(page.get('last_edited_time'))
        frontmatter = FrontmatterModel.from_data(
            {
                'uuid': self._uuid_generator.generate(),
                'area': entry['area'],
                'type': entry['type'],
                'tags': list(validated_tags),
                'date': created,
                'updated': updated,
                'source': list(entry['source']),
                'source_type': entry['source_type'],
                'file_type': entry['file_type'],
            },
            tag_registry=self._config.tag_registry,
            allowed_types=self._config.allowed_note_types,
        )
        body = render_notion_body(page, title=title, spec=spec, client=self._notion_backend.client)
        logical_path = f'{frontmatter.area.value}/{_safe_basename(title)}.md'
        markdown = self._codec.dumps(MarkdownDocument(frontmatter=frontmatter, body=body))
        embedding = tuple(float(value) for value in self._embedding_backend.embed_documents([markdown])[0])
        payload = {
            'title': title,
            'body': body,
            'frontmatter': frontmatter.ordered_dump(),
        }
        validate(instance=payload, schema=self._schema_builder.build_entry_schema())
        return InterpretedVaultEntry(
            title=title,
            logical_path=logical_path,
            body=body,
            frontmatter=frontmatter,
            markdown=markdown,
            embedding=embedding,
            tag_hierarchy=frontmatter.tag_hierarchy(self._config.tag_registry),
            source_page_id=source_page_id,
            datasource=datasource,
            raw_properties=dict(page.get('properties', {})),
        )


def _safe_basename(title: str) -> str:
    candidate = title.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'


def _render_body(page: Mapping[str, Any], *, title: str) -> str:
    properties = page.get('properties', {})
    lines = [f'# {title}', '', '## Notion properties']
    if not isinstance(properties, Mapping):
        return '\n'.join(lines)
    for property_name, raw_property in properties.items():
        if property_name in {'Name', 'title'}:
            continue
        rendered = _render_property(raw_property)
        if rendered:
            lines.append(f'- {property_name}: {rendered}')
    url = page.get('url')
    if isinstance(url, str) and url:
        lines.extend(['', '## Source', f'- url: {url}'])
    return '\n'.join(lines).strip()


def _render_property(raw_property: object) -> str:
    if not isinstance(raw_property, Mapping):
        return ''
    property_type = raw_property.get('type')
    if property_type == 'title':
        return _plain_text(raw_property.get('title', []))
    if property_type == 'rich_text':
        return _plain_text(raw_property.get('rich_text', []))
    if property_type in {'select', 'status'}:
        value = raw_property.get(property_type)
        if isinstance(value, Mapping):
            name = value.get('name')
            if isinstance(name, str):
                return name
        return ''
    if property_type == 'multi_select':
        values = raw_property.get('multi_select', [])
        if isinstance(values, list):
            return ', '.join(
                value.get('name', '')
                for value in values
                if isinstance(value, Mapping) and isinstance(value.get('name'), str)
            )
        return ''
    if property_type == 'date':
        value = raw_property.get('date')
        if isinstance(value, Mapping):
            start = value.get('start')
            end = value.get('end')
            if isinstance(start, str) and isinstance(end, str) and end:
                return f'{start} → {end}'
            if isinstance(start, str):
                return start
        return ''
    if property_type == 'checkbox':
        value = raw_property.get('checkbox')
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return ''
    if property_type == 'number':
        value = raw_property.get('number')
        if isinstance(value, int | float):
            return str(value)
        return ''
    if property_type == 'url':
        value = raw_property.get('url')
        return value if isinstance(value, str) else ''
    if property_type == 'email':
        value = raw_property.get('email')
        return value if isinstance(value, str) else ''
    if property_type == 'phone_number':
        value = raw_property.get('phone_number')
        return value if isinstance(value, str) else ''
    if property_type == 'relation':
        values = raw_property.get('relation', [])
        if isinstance(values, list):
            ids = [value.get('id', '') for value in values if isinstance(value, Mapping) and isinstance(value.get('id'), str)]
            return ', '.join(item for item in ids if item)
        return ''
    if property_type == 'formula':
        formula = raw_property.get('formula')
        if isinstance(formula, Mapping):
            for field in ('string', 'number', 'boolean'):
                value = formula.get(field)
                if value is not None:
                    return str(value)
        return ''
    if property_type == 'created_time':
        return _render_timestamp(raw_property.get('created_time'))
    if property_type == 'last_edited_time':
        return _render_timestamp(raw_property.get('last_edited_time'))
    return ''


def _render_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ''
    normalized = value.replace('Z', '+00:00')
    return datetime.fromisoformat(normalized).date().isoformat()


def _plain_text(items: object) -> str:
    if not isinstance(items, list):
        return ''
    chunks: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        plain_text = item.get('plain_text')
        if isinstance(plain_text, str):
            chunks.append(plain_text)
    return ''.join(chunks).strip()
