from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from plugins.memory.hermes_memory.backends.llm import StructuredTool
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.models import DATE_PATTERN, SOURCE_PATTERN, UUID_PATTERN

from .meta_loader import MetaLoader


class SchemaBuilder:
    def __init__(self, config: ConfigLayer, *, meta_loader: MetaLoader | None = None) -> None:
        self._config = config
        self._meta_loader = meta_loader or MetaLoader(config)

    def build_entry_schema(self) -> dict[str, Any]:
        type_descriptions = _parse_type_semantics(self._meta_loader.get('vault_spec.md').body)
        tags_description = _build_tags_description(self._config)
        frontmatter_schema: dict[str, Any] = {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'uuid': {
                    'type': 'string',
                    'pattern': UUID_PATTERN,
                    'description': 'Immutable Obsidian note UUID.',
                },
                'area': {
                    'type': 'string',
                    'enum': list(self._config.vault_spec.area_values),
                    'description': 'Provider-managed vault area. Only knowledge/ or inbox/ are allowed.',
                },
                'type': {
                    'type': 'string',
                    'enum': list(self._config.allowed_note_types),
                    'description': _build_type_description(type_descriptions),
                },
                'tags': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': list(self._config.tag_registry.tags),
                    },
                    'uniqueItems': True,
                    'description': tags_description,
                },
                'date': {
                    'type': 'string',
                    'pattern': DATE_PATTERN,
                    'description': 'Immutable creation date in YYYY-MM-DD.',
                },
                'updated': {
                    'type': 'string',
                    'pattern': DATE_PATTERN,
                    'description': 'Last updated date in YYYY-MM-DD.',
                },
                'source': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'pattern': SOURCE_PATTERN,
                    },
                    'uniqueItems': True,
                    'description': 'Immutable provenance list with notion:/web:/session:/attach:/multi: prefixes.',
                },
                'source_type': {
                    'type': 'string',
                    'enum': ['notion', 'gdrive', ''],
                },
                'file_type': {
                    'type': 'string',
                    'minLength': 1,
                    'description': 'Lowercase file extension without a leading dot, usually md.',
                },
            },
            'required': ['uuid', 'area', 'type', 'tags', 'date', 'updated', 'source', 'source_type', 'file_type'],
        }
        return {
            '$schema': 'https://json-schema.org/draft/2020-12/schema',
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'title': {
                    'type': 'string',
                    'minLength': 1,
                    'description': 'Human-readable note title used for the vault basename.',
                },
                'body': {
                    'type': 'string',
                    'description': 'Obsidian-native markdown only. Use #/## headings, convert H3+ to bullets, and never emit blockquotes.',
                },
                'frontmatter': frontmatter_schema,
            },
            'required': ['title', 'body', 'frontmatter'],
        }

    def build_openai_schema(self, *, name: str = 'hermes_vault_entry') -> dict[str, Any]:
        return {
            'name': name,
            'schema': self.build_entry_schema(),
            'strict': True,
        }

    def build_anthropic_tool(self, *, name: str = 'hermes_vault_entry', description: str = 'Return a Hermes vault entry object.') -> StructuredTool:
        return StructuredTool(name=name, description=description, input_schema=self.build_entry_schema())


def _parse_type_semantics(body: str) -> dict[str, str]:
    matches = re.findall(r'- `([^`]+)`: (.+)', body)
    return {note_type: description.strip() for note_type, description in matches}


def _build_tags_description(config: ConfigLayer) -> str:
    entries: list[str] = []
    for tag, entry in config.tag_registry.entries_by_tag.items():
        parent = '/'.join(entry.parent)
        entries.append(f'{tag} ({parent}): {entry.description}')
    return 'Allowed tags from TAGS.md. ' + ' | '.join(entries)


def _build_type_description(type_descriptions: Mapping[str, str]) -> str:
    parts = [f'{name}: {description}' for name, description in type_descriptions.items()]
    if 'custom' not in type_descriptions:
        parts.append('custom_types: additional type names supplied through config.custom_types')
    return 'Allowed note types from vault_spec.md. ' + ' | '.join(parts)
