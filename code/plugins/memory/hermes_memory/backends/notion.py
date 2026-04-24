from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import cached_property
import re
from typing import Any, Protocol

import yaml

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.config.settings import NotionDatabaseConfig, SyncProperty

from . import OptionalDependencyError


VaultEntryDict = dict[str, Any]


class NotionBackendProtocol(Protocol):
    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        ...

    def list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        ...

    def query_datasource(self, datasource: str) -> list[dict[str, Any]]:
        ...

    def read_vault_entries(self, datasource: str) -> list[VaultEntryDict]:
        ...

    def write_back_page(
        self,
        page_id: str,
        *,
        properties: Mapping[str, Any] | None = None,
        children: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class NotionRule:
    when: Mapping[str, Any]
    note_type: str | None
    required_tags: tuple[str, ...] = ()
    optional_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NotionDatasourceSpec:
    name: str
    db_id: str
    scan_mode: str | None
    area: str
    source_prefix: str
    source_type: str
    file_type: str
    static_type: str | None
    sync_properties: tuple[SyncProperty, ...] | None
    mapping_property: str | None
    mapping: Mapping[str, str | None]
    filter: Mapping[str, Any] | None
    rules: tuple[NotionRule, ...]
    include_when: Mapping[str, Any] | None = None
    exclude_when: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedNotionRoute:
    area: str
    note_type: str | None
    frontmatter_type: str
    required_tags: tuple[str, ...]
    optional_tags: tuple[str, ...]


class NotionBackend:
    """Notion datasource backend driven by config.yaml notion.databases."""

    def __init__(self, *, config: ConfigLayer, client: object | None = None) -> None:
        self._config = config
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    @cached_property
    def datasources(self) -> dict[str, NotionDatasourceSpec]:
        specs: dict[str, NotionDatasourceSpec] = {}
        configured_databases = self._config.settings.notion.databases
        if configured_databases:
            raw_specs = [_build_datasource_spec(database) for database in configured_databases]
        else:
            raw_specs = list(_load_bundled_datasource_specs(self._config.resources.notion_datasource_map_markdown))
        for spec in raw_specs:
            specs[spec.name] = spec
            specs[spec.db_id] = spec
        return specs

    def query_datasource(self, datasource: str, *, since: date | datetime | str | None = None) -> list[dict[str, Any]]:
        spec = self.datasources[datasource]
        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        while True:
            payload: dict[str, Any] = {
                'data_source_id': spec.db_id,
                'page_size': self._config.settings.notion.page_size,
                'start_cursor': next_cursor,
            }
            combined_filter = _compose_query_filter(spec.filter, since=since)
            if combined_filter is not None:
                payload['filter'] = combined_filter
            response = self.client.data_sources.query(**payload)
            page_results = response.get('results', [])
            if not isinstance(page_results, list):
                raise ValueError('Notion query response results must be a list')
            for raw_result in page_results:
                if isinstance(raw_result, dict):
                    results.append(raw_result)
            if not response.get('has_more'):
                break
            raw_cursor = response.get('next_cursor')
            next_cursor = raw_cursor if isinstance(raw_cursor, str) and raw_cursor else None
            if next_cursor is None:
                break
        return results

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        page = self.client.pages.retrieve(page_id=page_id)
        if not isinstance(page, dict):
            raise ValueError('Notion pages.retrieve response must be an object')
        return page

    def list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        while True:
            response = self.client.blocks.children.list(
                block_id=block_id,
                page_size=self._config.settings.notion.page_size,
                start_cursor=next_cursor,
            )
            page_results = response.get('results', [])
            if not isinstance(page_results, list):
                raise ValueError('Notion block children response results must be a list')
            for raw_result in page_results:
                if isinstance(raw_result, dict):
                    results.append(raw_result)
            if not response.get('has_more'):
                break
            raw_cursor = response.get('next_cursor')
            next_cursor = raw_cursor if isinstance(raw_cursor, str) and raw_cursor else None
            if next_cursor is None:
                break
        return results

    def read_vault_entries(self, datasource: str) -> list[VaultEntryDict]:
        spec = self.datasources[datasource]
        return [
            self._page_to_vault_entry(spec, page)
            for page in self.query_datasource(datasource)
            if self._is_included(spec, page) and not self._is_excluded(spec, page)
        ]

    def write_back_page(
        self,
        page_id: str,
        *,
        properties: Mapping[str, Any] | None = None,
        children: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        response: dict[str, Any] = {}
        if properties is not None:
            if not hasattr(self.client, 'pages') or not hasattr(self.client.pages, 'update'):
                raise AttributeError('Notion client does not expose pages.update for write-back')
            page_response = self.client.pages.update(page_id=page_id, properties=dict(properties))
            if not isinstance(page_response, dict):
                raise ValueError('Notion write-back page response must be an object')
            response['page'] = page_response
        if children:
            if not hasattr(self.client, 'blocks') or not hasattr(self.client.blocks, 'children'):
                raise AttributeError('Notion client does not expose blocks.children for write-back')
            append = getattr(self.client.blocks.children, 'append', None)
            if append is None:
                raise AttributeError('Notion client does not expose blocks.children.append for write-back')
            block_response = append(block_id=page_id, children=[dict(child) for child in children])
            if not isinstance(block_response, dict):
                raise ValueError('Notion write-back block response must be an object')
            response['blocks'] = block_response
        return response

    def _page_to_vault_entry(self, spec: NotionDatasourceSpec, page: Mapping[str, Any]) -> VaultEntryDict:
        resolved = self._resolve_route(spec, page)
        tag_values = list(resolved.required_tags)
        for tag in self._resolve_optional_tags(page, resolved.optional_tags):
            if tag not in tag_values:
                tag_values.append(tag)
        validated_tags = list(self._config.tag_registry.validate(tuple(tag_values))) if tag_values else []
        page_id = _require_string(page.get('id'), field='id')
        created = _iso_date(page.get('created_time'))
        updated = _iso_date(page.get('last_edited_time'))
        title = _extract_title(page)
        body = render_notion_body(page, title=title, spec=spec, client=self.client)
        return {
            'title': title,
            'body': body,
            'area': resolved.area,
            'type': resolved.frontmatter_type,
            'tags': validated_tags,
            'date': created,
            'updated': updated,
            'source': [f'{spec.source_prefix}{page_id}'],
            'source_type': spec.source_type,
            'file_type': spec.file_type,
            'notion_page_id': page_id,
            'properties': dict(page.get('properties', {})),
        }

    def _select_rule(self, spec: NotionDatasourceSpec, page: Mapping[str, Any]) -> NotionRule:
        for rule in spec.rules:
            if _matches_when(page, rule.when):
                return rule
        return NotionRule(when={}, note_type=None)

    def _resolve_route(self, spec: NotionDatasourceSpec, page: Mapping[str, Any]) -> ResolvedNotionRoute:
        rule = self._select_rule(spec, page)
        if rule.note_type is None:
            return ResolvedNotionRoute(
                area='inbox',
                note_type=None,
                frontmatter_type='knowledge',
                required_tags=rule.required_tags,
                optional_tags=rule.optional_tags,
            )
        return ResolvedNotionRoute(
            area=spec.area,
            note_type=rule.note_type,
            frontmatter_type=rule.note_type,
            required_tags=rule.required_tags,
            optional_tags=rule.optional_tags,
        )

    def _resolve_optional_tags(self, page: Mapping[str, Any], optional_tags: Sequence[str]) -> tuple[str, ...]:
        resolved: list[str] = []
        for tag in optional_tags:
            if tag != 'project_relation_registry_match_only':
                continue
            for relation_title in self._resolve_relation_titles(page, property_name='프로젝트'):
                if relation_title in self._config.tag_registry.entries_by_tag:
                    resolved.append(relation_title)
        return tuple(dict.fromkeys(resolved).keys())

    def _resolve_relation_titles(self, page: Mapping[str, Any], *, property_name: str) -> tuple[str, ...]:
        return _resolve_relation_titles(page, property_name=property_name, client=self.client)

    def _is_included(self, spec: NotionDatasourceSpec, page: Mapping[str, Any]) -> bool:
        return _matches_policy(page, spec.include_when, default=True)

    def _is_excluded(self, spec: NotionDatasourceSpec, page: Mapping[str, Any]) -> bool:
        return _matches_policy(page, spec.exclude_when, default=False)

    def _build_client(self) -> Any:
        notion_settings = self._config.settings.notion
        api_key = self._config.resolve_secret(
            yaml_value=notion_settings.api_key,
            service_name=notion_settings.service_name,
            env_vars=notion_settings.env_vars,
        )
        if api_key is None:
            raise RuntimeError(
                'Notion API key is not configured. Set env, ~/.openclaw/openclaw.json, or yaml, '
                'then run hermes-memory-doctor.'
            )
        try:
            from notion_client import Client
        except ImportError as exc:  # pragma: no cover
            raise OptionalDependencyError(
                'notion-client is not installed. Install the dependency, then run hermes-memory-doctor.'
            ) from exc
        return Client(auth=api_key, timeout_ms=int(notion_settings.timeout_seconds * 1000))


def _build_datasource_spec(database: NotionDatabaseConfig) -> NotionDatasourceSpec:
    mapping = dict(database.mapping or {})
    rules = _build_rules(database)
    scan_mode = database.scan_mode.strip() if isinstance(database.scan_mode, str) and database.scan_mode.strip() else None
    return NotionDatasourceSpec(
        name=database.name,
        db_id=database.id,
        scan_mode=scan_mode,
        area='knowledge',
        source_prefix='notion:',
        source_type='notion',
        file_type='md',
        static_type=database.type,
        sync_properties=tuple(database.sync_properties) if database.sync_properties is not None else None,
        mapping_property=database.mapping_property,
        mapping=mapping,
        filter=dict(database.filter) if database.filter is not None else None,
        rules=rules,
        include_when=None,
        exclude_when=None,
    )


def _build_rules(database: NotionDatabaseConfig) -> tuple[NotionRule, ...]:
    if database.type is not None:
        return (NotionRule(when={}, note_type=database.type),)
    assert database.mapping_property is not None
    assert database.mapping is not None
    rules: list[NotionRule] = []
    for source_value, target_type in database.mapping.items():
        rules.append(NotionRule(when={database.mapping_property: source_value}, note_type=target_type))
    return tuple(rules)


def _compose_query_filter(
    configured_filter: Mapping[str, Any] | None,
    *,
    since: date | datetime | str | None,
) -> Mapping[str, Any] | None:
    filters: list[Mapping[str, Any]] = []
    if configured_filter is not None:
        filters.append(dict(configured_filter))
    since_filter = _build_since_filter(since)
    if since_filter is not None:
        filters.append(since_filter)
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {'and': list(filters)}


def _build_since_filter(since: date | datetime | str | None) -> Mapping[str, Any] | None:
    if since is None:
        return None
    normalized = _normalize_since_value(since)
    return {
        'or': [
            {'timestamp': 'created_time', 'created_time': {'on_or_after': normalized}},
            {'timestamp': 'last_edited_time', 'last_edited_time': {'on_or_after': normalized}},
        ]
    }


def _normalize_since_value(since: date | datetime | str) -> str:
    if isinstance(since, datetime):
        aware = since if since.tzinfo is not None else since.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    if isinstance(since, date):
        return since.isoformat()
    normalized = since.strip()
    if not normalized:
        raise ValueError('since must not be empty')
    return normalized


def _load_bundled_datasource_specs(markdown: str) -> tuple[NotionDatasourceSpec, ...]:
    loaded = yaml.safe_load(_extract_fenced_yaml(markdown))
    if not isinstance(loaded, Mapping):
        raise ValueError('notion_datasource_map yaml block must deserialize to a mapping')
    datasources = loaded.get('datasources')
    if not isinstance(datasources, list):
        raise ValueError('notion_datasource_map yaml block must include datasources')
    return tuple(_parse_bundled_datasource_spec(item) for item in datasources)


def _parse_bundled_datasource_spec(raw: object) -> NotionDatasourceSpec:
    if not isinstance(raw, Mapping):
        raise ValueError('bundled datasource spec must be a mapping')
    mapping_block = raw.get('mapping')
    if not isinstance(mapping_block, Mapping):
        raise ValueError('bundled datasource spec must include a mapping block')
    rules_block = mapping_block.get('rules', [])
    if not isinstance(rules_block, list):
        raise ValueError('bundled datasource rules must be a list')
    rules = tuple(_parse_bundled_rule(item) for item in rules_block)
    include_when = _mapping_or_none(raw.get('include_when'))
    exclude_when = _mapping_or_none(raw.get('exclude_when'))
    scan_mode = raw.get('scan_mode')
    return NotionDatasourceSpec(
        name=_require_string(raw.get('name'), field='name'),
        db_id=_require_string(raw.get('db_id'), field='db_id'),
        scan_mode=scan_mode if isinstance(scan_mode, str) and scan_mode.strip() else None,
        area=_require_string(mapping_block.get('area', 'knowledge'), field='mapping.area'),
        source_prefix=_require_string(mapping_block.get('source_prefix', 'notion:'), field='mapping.source_prefix'),
        source_type=_require_string(mapping_block.get('source_type', 'notion'), field='mapping.source_type'),
        file_type=_require_string(mapping_block.get('file_type', 'md'), field='mapping.file_type'),
        static_type=None,
        sync_properties=None,
        mapping_property=None,
        mapping={},
        filter=None,
        rules=rules,
        include_when=include_when,
        exclude_when=exclude_when,
    )


def _parse_bundled_rule(raw: object) -> NotionRule:
    if not isinstance(raw, Mapping):
        raise ValueError('bundled routing rule must be a mapping')
    when = _mapping_or_none(raw.get('when')) or {}
    required_tags = tuple(str(item) for item in _list_or_empty(raw.get('required_tags')))
    optional_tags = tuple(str(item) for item in _list_or_empty(raw.get('optional_tags')))
    note_type = raw.get('type')
    if note_type is not None and not isinstance(note_type, str):
        raise ValueError('bundled routing rule type must be a string or null')
    return NotionRule(
        when=when,
        note_type=note_type,
        required_tags=required_tags,
        optional_tags=optional_tags,
    )


def _mapping_or_none(value: object) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


def _list_or_empty(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _extract_fenced_yaml(markdown: str) -> str:
    match = re.search(r'```yaml\n(?P<body>.*?)\n```', markdown, re.DOTALL)
    if match is None:
        raise ValueError('yaml fenced block not found')
    return match.group('body')


def _matches_policy(page: Mapping[str, Any], policy: Mapping[str, Any] | None, *, default: bool) -> bool:
    if policy is None:
        return default
    if policy.get('all_rows') is True:
        return True
    property_name = policy.get('property')
    if not isinstance(property_name, str) or not property_name:
        return default
    actual = _property_plain_text(page, property_name)
    candidates = policy.get('in')
    if isinstance(candidates, list):
        return actual in {str(item) for item in candidates}
    equals = policy.get('equals')
    if equals is not None:
        return actual == str(equals)
    return default


def _matches_when(page: Mapping[str, Any], conditions: Mapping[str, Any]) -> bool:
    for key, expected in conditions.items():
        if key.endswith('_in'):
            property_name = key[:-3]
            actual = _property_plain_text(page, property_name)
            if not isinstance(expected, Sequence):
                return False
            if actual not in {str(item) for item in expected}:
                return False
            continue
        actual = _property_plain_text(page, key)
        if actual != str(expected):
            return False
    return True


def _property_plain_text(page: Mapping[str, Any], property_name: str) -> str:
    properties = page.get('properties', {})
    if not isinstance(properties, Mapping):
        return ''
    prop = properties.get(property_name)
    if not isinstance(prop, Mapping):
        return ''
    prop_type = prop.get('type')
    if not isinstance(prop_type, str) or not prop_type:
        return ''
    return _render_property_value(page, property_name=property_name, property_type=prop_type, raw_property=prop)


def render_notion_body(
    page: Mapping[str, Any],
    *,
    title: str,
    spec: NotionDatasourceSpec,
    client: Any | None = None,
) -> str:
    lines = [f'# {title}']
    property_lines = _render_body_property_lines(page, spec=spec, client=client)
    if property_lines:
        lines.extend(['', '## Notion properties', *property_lines])
    if not (spec.sync_properties is not None and not spec.sync_properties):
        url = page.get('url')
        if isinstance(url, str) and url:
            lines.extend(['', '## Source', f'- url: {url}'])
    return '\n'.join(lines).strip()


def _render_body_property_lines(
    page: Mapping[str, Any],
    *,
    spec: NotionDatasourceSpec,
    client: Any | None = None,
) -> list[str]:
    lines: list[str] = []
    for property_name, property_type, raw_property in _iter_renderable_properties(page, spec=spec):
        rendered = _render_property_value(
            page,
            property_name=property_name,
            property_type=property_type,
            raw_property=raw_property,
            client=client,
        )
        if rendered:
            lines.append(f'- {property_name}: {rendered}')
    return lines


def _iter_renderable_properties(
    page: Mapping[str, Any],
    *,
    spec: NotionDatasourceSpec,
) -> tuple[tuple[str, str, Mapping[str, Any]], ...]:
    properties = page.get('properties', {})
    if not isinstance(properties, Mapping):
        return ()
    if spec.sync_properties is None:
        selected: list[tuple[str, str, Mapping[str, Any]]] = []
        for property_name, raw_property in properties.items():
            if property_name in {'Name', 'title'} or not isinstance(raw_property, Mapping):
                continue
            property_type = raw_property.get('type')
            if not isinstance(property_type, str) or property_type == 'title':
                continue
            selected.append((property_name, property_type, raw_property))
        return tuple(selected)

    selected = []
    for sync_property in spec.sync_properties:
        raw_property = properties.get(sync_property.name)
        if isinstance(raw_property, Mapping):
            selected.append((sync_property.name, sync_property.type, raw_property))
    return tuple(selected)


def _render_property_value(
    page: Mapping[str, Any],
    *,
    property_name: str,
    property_type: str,
    raw_property: Mapping[str, Any],
    client: Any | None = None,
) -> str:
    if property_type == 'title':
        return _rich_text_plain_text(raw_property.get('title', []))
    if property_type == 'rich_text':
        return _rich_text_plain_text(raw_property.get('rich_text', []))
    if property_type in {'select', 'status'}:
        item = raw_property.get(property_type)
        if isinstance(item, Mapping):
            name = item.get('name')
            if isinstance(name, str):
                return name
        return ''
    if property_type == 'multi_select':
        items = raw_property.get('multi_select', [])
        if isinstance(items, list):
            names = [item.get('name', '') for item in items if isinstance(item, Mapping) and isinstance(item.get('name'), str)]
            return ', '.join(name for name in names if name)
        return ''
    if property_type == 'date':
        return _render_date_value(raw_property.get('date'))
    if property_type == 'person':
        return _render_people(raw_property.get('people'))
    if property_type == 'checkbox':
        value = raw_property.get('checkbox')
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return ''
    if property_type == 'number':
        value = raw_property.get('number')
        return '' if value is None else str(value)
    if property_type in {'url', 'email', 'phone_number'}:
        value = raw_property.get(property_type)
        return value if isinstance(value, str) else ''
    if property_type == 'files':
        return _render_files(raw_property.get('files'))
    if property_type == 'relation':
        return _render_relation(page, property_name=property_name, raw_property=raw_property, client=client)
    if property_type == 'created_time':
        return _normalize_timestamp(raw_property.get('created_time'))
    if property_type == 'last_edited_time':
        return _normalize_timestamp(raw_property.get('last_edited_time'))
    if property_type == 'created_by':
        return _render_user(raw_property.get('created_by'))
    if property_type == 'last_edited_by':
        return _render_user(raw_property.get('last_edited_by'))
    if property_type == 'formula':
        return _render_formula(raw_property.get('formula'))
    if property_type == 'rollup':
        return _render_rollup(raw_property.get('rollup'))
    return ''


def _render_date_value(value: object) -> str:
    if not isinstance(value, Mapping):
        return ''
    start = _normalize_date_like(value.get('start'))
    end = _normalize_date_like(value.get('end'))
    if start and end:
        return f'{start} → {end}'
    return start


def _normalize_date_like(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ''
    try:
        if 'T' in value or value.endswith('Z'):
            return datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat()
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return value


def _normalize_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ''
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat()
    except ValueError:
        return value


def _render_people(value: object) -> str:
    if not isinstance(value, list):
        return ''
    names = [_render_user(item) for item in value if isinstance(item, Mapping)]
    return ', '.join(name for name in names if name)


def _render_user(value: object) -> str:
    if not isinstance(value, Mapping):
        return ''
    name = value.get('name')
    if isinstance(name, str) and name:
        return name
    person = value.get('person')
    if isinstance(person, Mapping):
        email = person.get('email')
        if isinstance(email, str):
            return email
    return ''


def _render_files(value: object) -> str:
    if not isinstance(value, list):
        return ''
    rendered: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = item.get('name')
        url = ''
        file_value = item.get('file')
        if isinstance(file_value, Mapping):
            raw_url = file_value.get('url')
            if isinstance(raw_url, str):
                url = raw_url
        external_value = item.get('external')
        if isinstance(external_value, Mapping):
            raw_url = external_value.get('url')
            if isinstance(raw_url, str):
                url = raw_url
        if isinstance(name, str) and name and url:
            rendered.append(f'{name} ({url})')
            continue
        if isinstance(name, str) and name:
            rendered.append(name)
            continue
        if url:
            rendered.append(url)
    return ', '.join(rendered)


def _render_relation(
    page: Mapping[str, Any],
    *,
    property_name: str,
    raw_property: Mapping[str, Any],
    client: Any | None = None,
) -> str:
    titles = _resolve_relation_titles(page, property_name=property_name, raw_property=raw_property, client=client)
    if titles:
        return ', '.join(titles)
    relation_items = raw_property.get('relation', [])
    if not isinstance(relation_items, list):
        return ''
    ids = [item.get('id', '') for item in relation_items if isinstance(item, Mapping) and isinstance(item.get('id'), str)]
    return ', '.join(item for item in ids if item)


def _resolve_relation_titles(
    page: Mapping[str, Any],
    *,
    property_name: str,
    raw_property: Mapping[str, Any] | None = None,
    client: Any | None = None,
) -> tuple[str, ...]:
    relation_property = raw_property
    if relation_property is None:
        properties = page.get('properties', {})
        if not isinstance(properties, Mapping):
            return ()
        candidate = properties.get(property_name)
        if not isinstance(candidate, Mapping):
            return ()
        relation_property = candidate
    if relation_property.get('type') != 'relation':
        return ()
    relation_items = relation_property.get('relation', [])
    if not isinstance(relation_items, list):
        return ()
    if client is None or not hasattr(client, 'pages') or not hasattr(client.pages, 'retrieve'):
        return ()
    titles: list[str] = []
    for item in relation_items:
        if not isinstance(item, Mapping):
            continue
        relation_id = item.get('id')
        if not isinstance(relation_id, str) or not relation_id:
            continue
        related_page = client.pages.retrieve(page_id=relation_id)
        if isinstance(related_page, Mapping):
            titles.append(_extract_title(related_page))
    return tuple(title for title in titles if title)


def _render_formula(value: object) -> str:
    if not isinstance(value, Mapping):
        return ''
    formula_type = value.get('type')
    if formula_type == 'date':
        return _render_date_value(value.get('date'))
    for candidate_key in ('string', 'number', 'boolean'):
        candidate = value.get(candidate_key)
        if candidate is None:
            continue
        if isinstance(candidate, bool):
            return 'true' if candidate else 'false'
        return str(candidate)
    return ''


def _render_rollup(value: object) -> str:
    if not isinstance(value, Mapping):
        return ''
    rollup_type = value.get('type')
    if rollup_type == 'date':
        return _render_date_value(value.get('date'))
    if rollup_type == 'array':
        array_value = value.get('array')
        if not isinstance(array_value, list):
            return ''
        rendered_items = [_render_rollup_array_item(item) for item in array_value]
        return ', '.join(item for item in rendered_items if item)
    candidate = value.get(rollup_type) if isinstance(rollup_type, str) else None
    if candidate is None:
        return ''
    if isinstance(candidate, bool):
        return 'true' if candidate else 'false'
    return str(candidate)


def _render_rollup_array_item(value: object) -> str:
    if not isinstance(value, Mapping):
        return ''
    value_type = value.get('type')
    if not isinstance(value_type, str) or not value_type:
        return ''
    return _render_property_value({}, property_name='', property_type=value_type, raw_property=value)


def _extract_title(page: Mapping[str, Any]) -> str:
    properties = page.get('properties', {})
    if isinstance(properties, Mapping):
        for value in properties.values():
            if not isinstance(value, Mapping):
                continue
            if value.get('type') != 'title':
                continue
            title = _rich_text_plain_text(value.get('title', []))
            if title:
                return title
    url = page.get('url')
    if isinstance(url, str) and url.strip():
        return url.rstrip('/').split('/')[-1]
    page_id = page.get('id')
    if isinstance(page_id, str):
        return page_id
    return 'untitled'


def _rich_text_plain_text(items: object) -> str:
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


def _require_string(value: object, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f'{field} must be a non-empty string')


def _iso_date(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError('Notion page timestamp must be a non-empty string')
    normalized = value.replace('Z', '+00:00')
    parsed = datetime.fromisoformat(normalized)
    return parsed.date().isoformat()
