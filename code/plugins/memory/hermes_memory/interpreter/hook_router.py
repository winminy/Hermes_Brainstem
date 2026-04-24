from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re

import yaml

from plugins.memory.hermes_memory.backends.notion import NotionBackend, NotionDatasourceSpec, NotionRule
from plugins.memory.hermes_memory.config.layer import ConfigLayer

from .meta_loader import MetaLoader


@dataclass(frozen=True, slots=True)
class HookDefinition:
    name: str
    trigger: str
    cadence: str
    downstream: tuple[str, ...]
    excludes: tuple[str, ...]
    skill_binding: str
    datasource_scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HookRoute:
    definition: HookDefinition
    datasource_id: str | None = None
    notion_type: str | None = None
    file_type: str | None = None
    note_type: str | None = None
    area: str | None = None

    def matches(self, *, datasource_id: str | None, notion_type: str | None, file_type: str | None) -> bool:
        if self.datasource_id is not None and self.datasource_id != datasource_id:
            return False
        if self.notion_type is not None and self.notion_type != notion_type:
            return False
        if self.file_type is not None and self.file_type != file_type:
            return False
        return True


class HookRouter:
    def __init__(
        self,
        config: ConfigLayer,
        *,
        meta_loader: MetaLoader | None = None,
        notion_backend: NotionBackend | None = None,
    ) -> None:
        self._config = config
        self._meta_loader = meta_loader or MetaLoader(config)
        self._notion_backend = notion_backend or NotionBackend(config=config, client=object())
        self._definitions: dict[str, HookDefinition] = {}
        self._routes: dict[str, tuple[HookRoute, ...]] = {}
        self.reload()

    def reload(self) -> tuple[str, ...]:
        changed = self._meta_loader.reload()
        registry_doc = self._meta_loader.get('self_reference/hook_registry.md')
        loaded = yaml.safe_load(_extract_fenced_yaml(registry_doc.text))
        if not isinstance(loaded, Mapping):
            raise ValueError('hook_registry yaml block must deserialize to a mapping')
        hooks = loaded.get('hooks')
        if not isinstance(hooks, list):
            raise ValueError('hook_registry yaml block must include hooks')
        definitions: dict[str, HookDefinition] = {}
        routes: dict[str, tuple[HookRoute, ...]] = {}
        for raw_hook in hooks:
            definition = _parse_hook(raw_hook)
            definitions[definition.name] = definition
            routes[definition.name] = self._build_routes(definition)
        self._definitions = definitions
        self._routes = routes
        return changed

    def definition_for(self, name: str) -> HookDefinition:
        return self._definitions[name]

    def routes_for(self, name: str) -> tuple[HookRoute, ...]:
        return self._routes.get(name, ())

    def route(self, name: str, *, datasource_id: str | None = None, notion_type: str | None = None, file_type: str | None = None) -> HookRoute:
        for route in self.routes_for(name):
            if route.matches(datasource_id=datasource_id, notion_type=notion_type, file_type=file_type):
                return route
        if name in self._definitions:
            return HookRoute(definition=self._definitions[name])
        raise KeyError(name)

    def _build_routes(self, definition: HookDefinition) -> tuple[HookRoute, ...]:
        if definition.name != 'notion_sync':
            return (HookRoute(definition=definition),)
        conditional_routes: list[HookRoute] = []
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for spec in {spec.db_id: spec for spec in self._notion_backend.datasources.values()}.values():
            for route in _routes_from_spec(definition, spec):
                key = (route.datasource_id, route.notion_type, route.file_type)
                if key in seen:
                    continue
                seen.add(key)
                conditional_routes.append(route)
        return tuple(conditional_routes)


def _parse_hook(raw_hook: object) -> HookDefinition:
    if not isinstance(raw_hook, Mapping):
        raise ValueError('hook definition must be a mapping')
    downstream = raw_hook.get('downstream', [])
    excludes = raw_hook.get('excludes', [])
    datasource_scope = raw_hook.get('datasource_scope', [])
    if not isinstance(downstream, list) or not isinstance(excludes, list) or not isinstance(datasource_scope, list):
        raise ValueError('hook list fields must be lists')
    return HookDefinition(
        name=_require_string(raw_hook.get('name'), field='hook.name'),
        trigger=_require_string(raw_hook.get('trigger'), field='hook.trigger'),
        cadence=_require_string(raw_hook.get('cadence'), field='hook.cadence'),
        downstream=tuple(str(item) for item in downstream),
        excludes=tuple(str(item) for item in excludes),
        skill_binding=_require_string(raw_hook.get('skill_binding'), field='hook.skill_binding'),
        datasource_scope=tuple(str(item) for item in datasource_scope),
    )


def _routes_from_spec(definition: HookDefinition, spec: NotionDatasourceSpec) -> tuple[HookRoute, ...]:
    routes: list[HookRoute] = []
    for rule in spec.rules:
        notion_types = _notion_types_from_rule(rule)
        if not notion_types:
            notion_types = (None,)
        for notion_type in notion_types:
            routes.append(
                HookRoute(
                    definition=definition,
                    datasource_id=spec.db_id,
                    notion_type=notion_type,
                    file_type=spec.file_type,
                    note_type=rule.note_type,
                    area=spec.area,
                )
            )
    return tuple(routes)


def _notion_types_from_rule(rule: NotionRule) -> tuple[str | None, ...]:
    for key, value in rule.when.items():
        if key.endswith('_in') and isinstance(value, list):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
    return (None,)


def _require_string(value: object, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f'{field} must be a non-empty string')


def _extract_fenced_yaml(markdown: str) -> str:
    match = re.search(r'```yaml\n(?P<body>.*?)\n```', markdown, re.DOTALL)
    if match is None:
        raise ValueError('yaml fenced block not found')
    return match.group('body')
