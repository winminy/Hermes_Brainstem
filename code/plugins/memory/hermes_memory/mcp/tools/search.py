from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from plugins.memory.hermes_memory.mcp.errors import raise_invalid_params
from plugins.memory.hermes_memory.mcp.schema_loader import load_schema
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.search import SearchFilters, direct_search, semantic_search

from .base import ManagedTool


def build_search_tool(services: HermesMemoryServices) -> ManagedTool:
    def handler(arguments: Mapping[str, Any]) -> dict[str, Any]:
        query = _require_non_empty_string(arguments.get('query'), field='query')
        mode = _optional_string(arguments.get('mode')) or 'semantic'
        if mode not in {'semantic', 'direct'}:
            raise_invalid_params('mode must be "semantic" or "direct"', data={'field': 'mode'})
        top_k = _positive_int(arguments.get('top_k', 5), field='top_k')
        filters_payload = arguments.get('filters')
        filters_map = filters_payload if isinstance(filters_payload, Mapping) else {}
        filters = SearchFilters(
            area=_optional_string(filters_map.get('area')),
            type=_optional_string(filters_map.get('type')),
            tags=_string_tuple(filters_map.get('tags')),
            tag_match_mode=_tag_match_mode(filters_map.get('tag_match_mode')),
            source_type=_optional_string(filters_map.get('source_type')),
            file_type=_optional_string(filters_map.get('file_type')),
            date_from=_optional_string(filters_map.get('date_from')),
            date_to=_optional_string(filters_map.get('date_to')),
            updated_from=_optional_string(filters_map.get('updated_from')),
            updated_to=_optional_string(filters_map.get('updated_to')),
        )
        vault_root = services.config.settings.vault_root
        if vault_root is None:
            raise_invalid_params('vault_root is not configured', data={'field': 'vault_root'})
        hits = (
            direct_search(query, config=services.config, filters=filters, vault_root=vault_root, top_k=top_k)
            if mode == 'direct'
            else semantic_search(
                query,
                services.lightrag_backend,
                config=services.config,
                filters=filters,
                vault_root=vault_root,
                top_k=top_k,
            )
        )
        return {
            'requested_mode': mode,
            'count': len(hits),
            'hits': [
                {
                    'score': hit.score,
                    'snippet': hit.snippet,
                    'origin': hit.origin,
                    'metadata': {
                        'title': hit.metadata.title,
                        'relative_path': hit.metadata.relative_path,
                        'uuid': hit.metadata.uuid,
                        'area': hit.metadata.area,
                        'type': hit.metadata.type,
                        'tags': list(hit.metadata.tags),
                        'date': hit.metadata.date,
                        'updated': hit.metadata.updated,
                        'source': list(hit.metadata.source),
                        'source_type': hit.metadata.source_type,
                        'file_type': hit.metadata.file_type,
                    },
                }
                for hit in hits
            ],
        }

    return ManagedTool(
        name='search',
        title='Hermes Search',
        description='Phase 9 search wrapper with frontmatter filters and tag_match_mode.',
        input_schema=load_schema('search.input.json'),
        output_schema=load_schema('search.output.json'),
        handler=handler,
    )


def _require_non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise_invalid_params(f'{field} must be a non-empty string', data={'field': field})
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise_invalid_params('expected a string value')
    stripped = value.strip()
    return stripped or None


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise_invalid_params(f'{field} must be a positive integer', data={'field': field})
    return value


def _tag_match_mode(value: object) -> Literal['all', 'any']:
    resolved = _optional_string(value)
    if resolved is None or resolved == 'all':
        return 'all'
    if resolved == 'any':
        return 'any'
    raise_invalid_params('tag_match_mode must be "all" or "any"', data={'field': 'filters.tag_match_mode'})


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise_invalid_params('tags must be an array of strings', data={'field': 'filters.tags'})
    return tuple(item.strip() for item in value if item.strip())
