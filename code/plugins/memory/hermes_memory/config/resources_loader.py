from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from importlib.resources import files
from importlib.resources.abc import Traversable
import re

import yaml

from plugins.memory.hermes_memory.core.models import Area, BUILTIN_NOTE_TYPES

from .settings import HermesMemorySettings


_SOURCE_PREFIX_RE = re.compile(r"`(notion|web|session|attach|multi):`")


@dataclass(frozen=True, slots=True)
class TagRegistryEntry:
    tag: str
    parent: tuple[str, ...]
    description: str
    llm_visible: bool


@dataclass(frozen=True, slots=True)
class TagRegistry:
    entries_by_tag: dict[str, TagRegistryEntry]

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(self.entries_by_tag.keys())

    def hierarchy_for(self, tag: str) -> tuple[str, ...]:
        return self.entries_by_tag[tag].parent

    def validate(self, tags: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        normalized: list[str] = []
        invalid: list[str] = []
        for tag in tags:
            if tag in seen:
                raise ValueError(f'duplicate tag is not allowed: {tag}')
            seen.add(tag)
            entry = self.entries_by_tag.get(tag)
            if entry is None:
                invalid.append(tag)
                continue
            if not entry.parent:
                raise ValueError(f'tag registry entry has no hierarchy parent: {tag}')
            normalized.append(tag)
        if invalid:
            raise ValueError(f"unregistered tags: {', '.join(invalid)}")
        return tuple(normalized)


@dataclass(frozen=True, slots=True)
class VaultSpecContract:
    area_values: tuple[str, ...]
    type_values: tuple[str, ...]
    source_prefixes: tuple[str, ...]
    provider_managed_note_roots: tuple[str, ...]
    attachment_root_template: str
    quarantine_root_template: str


class ResourceLoader:
    def __init__(self, settings: HermesMemorySettings) -> None:
        self._settings = settings

    def read_text(self, relative_path: str) -> str:
        resource_root = files(self._settings.resource_package)
        resource = resource_root.joinpath(*relative_path.split('/'))
        return resource.read_text(encoding='utf-8')

    @cached_property
    def tags_markdown(self) -> str:
        return self.read_text(f'{self._settings.resource_system_root}/TAGS.md')

    @cached_property
    def vault_spec_markdown(self) -> str:
        return self.read_text(f'{self._settings.resource_system_root}/vault_spec.md')

    @cached_property
    def notion_datasource_map_markdown(self) -> str:
        return self.read_text(f'{self._settings.resource_system_root}/notion_datasource_map.md')

    @cached_property
    def tag_registry(self) -> TagRegistry:
        return _parse_tags_registry(self.tags_markdown)

    @cached_property
    def vault_spec_contract(self) -> VaultSpecContract:
        return _parse_vault_spec_contract(self.vault_spec_markdown)

    def system_markdown_paths(self) -> tuple[str, ...]:
        resource_root = files(self._settings.resource_package).joinpath(self._settings.resource_system_root)
        return tuple(sorted(_iter_markdown_paths(resource_root)))


def _iter_markdown_paths(root: Traversable, prefix: str = '') -> Iterator[str]:
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        relative_name = f'{prefix}{child.name}'
        if child.is_dir():
            yield from _iter_markdown_paths(child, prefix=f'{relative_name}/')
        elif child.is_file() and child.name.endswith('.md'):
            yield relative_name


def _parse_tags_registry(markdown: str) -> TagRegistry:
    yaml_block = _extract_fenced_yaml(markdown)
    loaded = yaml.safe_load(yaml_block)
    if not isinstance(loaded, dict):
        raise ValueError('TAGS.md registry block must deserialize to a mapping')
    registry = loaded.get('registry')
    if not isinstance(registry, list):
        raise ValueError('TAGS.md registry block must include a registry list')

    entries: dict[str, TagRegistryEntry] = {}
    for raw_entry in registry:
        if not isinstance(raw_entry, dict):
            raise ValueError('each tag registry entry must be a mapping')
        tag = raw_entry.get('tag')
        parent = raw_entry.get('parent')
        description = raw_entry.get('description')
        llm_visible = raw_entry.get('llm_visible')
        if not isinstance(tag, str) or not isinstance(parent, str) or not isinstance(description, str) or not isinstance(llm_visible, bool):
            raise ValueError('tag registry entries must contain tag/parent/description/llm_visible')
        hierarchy = tuple(part for part in parent.split('/') if part)
        if not hierarchy:
            raise ValueError(f'tag registry parent must contain at least one hierarchy segment: {tag}')
        if tag in entries:
            raise ValueError(f'duplicate tag registry entry: {tag}')
        entries[tag] = TagRegistryEntry(tag=tag, parent=hierarchy, description=description, llm_visible=llm_visible)
    return TagRegistry(entries_by_tag=entries)


def _parse_vault_spec_contract(markdown: str) -> VaultSpecContract:
    area_values = _parse_inline_enum(markdown, 'area')
    type_values = _parse_inline_enum(markdown, 'type')
    note_roots = _parse_backticked_values(markdown, 'provider_managed_note_roots')
    attachment_root_template = _parse_backticked_scalar(markdown, 'provider_managed_attachment_root')
    quarantine_root_template = _parse_backticked_scalar(markdown, 'provider_managed_quarantine_root')
    prefixes = tuple(dict.fromkeys(_SOURCE_PREFIX_RE.findall(markdown)).keys())
    if not prefixes:
        raise ValueError('source prefixes could not be parsed from vault_spec.md')
    return VaultSpecContract(
        area_values=area_values,
        type_values=type_values,
        source_prefixes=prefixes,
        provider_managed_note_roots=note_roots,
        attachment_root_template=attachment_root_template,
        quarantine_root_template=quarantine_root_template,
    )


def _parse_inline_enum(markdown: str, field_name: str) -> tuple[str, ...]:
    pattern = re.compile(r"\| `" + re.escape(field_name) + r"` \| enum (?P<body>[^|]+)\|")
    match = pattern.search(markdown)
    if match is None:
        raise ValueError(f'enum definition for {field_name} not found in vault_spec.md')
    body = match.group('body')
    values = re.findall(r'`([^`]+)`', body)
    if not values:
        values = [part.strip().strip('"') for part in body.split(',') if part.strip()]
    return tuple(values)


def _parse_backticked_values(markdown: str, key: str) -> tuple[str, ...]:
    pattern = re.compile(rf'- {re.escape(key)}: (?P<body>.+)')
    match = pattern.search(markdown)
    if match is None:
        raise ValueError(f'{key} not found in vault_spec.md')
    return tuple(re.findall(r'`([^`]+)`', match.group('body')))


def _parse_backticked_scalar(markdown: str, key: str) -> str:
    values = _parse_backticked_values(markdown, key)
    if len(values) != 1:
        raise ValueError(f'{key} must resolve to exactly one value')
    return values[0]


def _extract_fenced_yaml(markdown: str) -> str:
    match = re.search(r'```yaml\n(?P<body>.*?)\n```', markdown, re.DOTALL)
    if match is None:
        raise ValueError('yaml fenced block not found')
    return match.group('body')


def assert_resource_contracts(settings: HermesMemorySettings, loader: ResourceLoader) -> None:
    contract = loader.vault_spec_contract
    if tuple(area.value for area in Area) != contract.area_values:
        raise ValueError('bundled vault_spec area enum does not match Area enum')
    if contract.type_values != BUILTIN_NOTE_TYPES:
        raise ValueError('bundled vault_spec type enum does not match NoteType enum')
    expected_roots = tuple(f'{area.value}/' for area in Area)
    if contract.provider_managed_note_roots != expected_roots:
        raise ValueError('bundled vault_spec note roots do not match Area enum values')
    if settings.quarantine_dirname not in contract.quarantine_root_template:
        raise ValueError('bundled vault_spec quarantine root does not include configured quarantine dirname')
