from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
from pathlib import Path
import re
from typing import Any

import importlib
import yaml

from plugins.memory.hermes_memory.config.layer import ConfigLayer

python_frontmatter: Any
mistune: Any

try:
    python_frontmatter = importlib.import_module('frontmatter')
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    python_frontmatter = None

try:
    mistune = importlib.import_module('mistune')
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    mistune = None


REQUIRED_META_FILES: tuple[str, ...] = (
    'TAGS.md',
    'vault_spec.md',
    'notion_datasource_map.md',
    'data_ops/binary_policy.md',
    'data_ops/file_policy.md',
    'data_ops/retention.md',
    'self_reference/hook_registry.md',
    'self_reference/persist_policy.md',
    'self_reference/quarantine_policy.md',
    'self_reference/scope_policy.md',
    'skills/skill_registry.md',
    'skills/skill_spec.md',
    'skills/default/notion_sync.md',
    'skills/default/persist_attach.md',
    'skills/default/quarantine_sweep.md',
    'skills/default/session_close.md',
)


@dataclass(frozen=True, slots=True)
class MetaDocument:
    relative_path: str
    path: Path
    text: str
    frontmatter: Mapping[str, Any]
    body: str
    headings: tuple[str, ...]
    fingerprint: str


class MetaLoader:
    def __init__(self, config: ConfigLayer) -> None:
        self._config = config
        self._documents: dict[str, MetaDocument] = {}
        self._fingerprints: dict[str, str] = {}

    @property
    def system_root(self) -> Path:
        package = import_module(self._config.settings.resource_package)
        package_file = getattr(package, '__file__', None)
        if not isinstance(package_file, str):
            raise RuntimeError('resource package does not expose a filesystem path')
        return Path(package_file).resolve().parent / self._config.settings.resource_system_root

    def documents(self) -> Mapping[str, MetaDocument]:
        if not self._documents:
            self.reload()
        return dict(self._documents)

    def get(self, relative_path: str) -> MetaDocument:
        return self.documents()[relative_path]

    def reload(self) -> tuple[str, ...]:
        documents: dict[str, MetaDocument] = {}
        fingerprints: dict[str, str] = {}
        for relative_path in REQUIRED_META_FILES:
            path = self.system_root / relative_path
            text = path.read_text(encoding='utf-8')
            frontmatter, body = _parse_frontmatter(text)
            fingerprint = sha256(text.encode('utf-8')).hexdigest()
            documents[relative_path] = MetaDocument(
                relative_path=relative_path,
                path=path,
                text=text,
                frontmatter=frontmatter,
                body=body,
                headings=_extract_headings(body),
                fingerprint=fingerprint,
            )
            fingerprints[relative_path] = fingerprint
        changed = tuple(
            sorted(
                {
                    relative_path
                    for relative_path, fingerprint in fingerprints.items()
                    if self._fingerprints.get(relative_path) != fingerprint
                }
                | {relative_path for relative_path in self._fingerprints if relative_path not in fingerprints}
            )
        )
        self._documents = documents
        self._fingerprints = fingerprints
        return changed


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if python_frontmatter is not None:
        post = python_frontmatter.loads(text)
        return dict(post.metadata), str(post.content)

    match = re.match(r'^---\n(?P<meta>.*?)\n---\n?(?P<body>.*)$', text, re.DOTALL)
    if match is None:
        return {}, text
    loaded = yaml.safe_load(match.group('meta'))
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError('meta frontmatter must deserialize to a mapping')
    return loaded, match.group('body')


def _extract_headings(body: str) -> tuple[str, ...]:
    if mistune is not None:
        renderer = mistune.create_markdown(renderer='ast')
        tokens = renderer(body)
        parsed_headings = [
            _ast_text(token.get('children', []))
            for token in tokens
            if isinstance(token, dict) and token.get('type') == 'heading'
        ]
        return tuple(heading for heading in parsed_headings if heading)
    headings: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            headings.append(stripped.lstrip('#').strip())
    return tuple(headings)


def _ast_text(nodes: object) -> str:
    if not isinstance(nodes, list):
        return ''
    chunks: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        raw = node.get('raw')
        if isinstance(raw, str):
            chunks.append(raw)
        children = node.get('children')
        if isinstance(children, list):
            child_text = _ast_text(children)
            if child_text:
                chunks.append(child_text)
    return ''.join(chunks).strip()
