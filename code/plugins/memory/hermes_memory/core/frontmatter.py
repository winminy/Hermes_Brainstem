from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any

import yaml

try:
    import frontmatter as python_frontmatter  # type: ignore[import-untyped]
except ModuleNotFoundError:
    python_frontmatter = None

from .models import FrontmatterModel

if TYPE_CHECKING:
    from plugins.memory.hermes_memory.config.layer import ConfigLayer


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    frontmatter: FrontmatterModel
    body: str


class FrontmatterCodec:
    def __init__(self, config: ConfigLayer) -> None:
        self._config = config

    def loads(self, text: str) -> MarkdownDocument:
        metadata, body = _parse_document(text)
        if not isinstance(metadata, dict):
            raise ValueError('frontmatter metadata must deserialize to a mapping')
        model = FrontmatterModel.from_data(
            metadata,
            tag_registry=self._config.tag_registry,
            allowed_types=self._config.allowed_note_types,
        )
        return MarkdownDocument(frontmatter=model, body=body)

    def dumps(self, document: MarkdownDocument) -> str:
        validated = FrontmatterModel.from_data(
            document.frontmatter.ordered_dump(),
            tag_registry=self._config.tag_registry,
            allowed_types=self._config.allowed_note_types,
        )
        payload = _render_frontmatter(validated)
        body = document.body.lstrip('\n')
        if body:
            return f'---\n{payload}\n---\n\n{body}\n'
        return f'---\n{payload}\n---\n'


def _render_frontmatter(model: FrontmatterModel) -> str:
    lines = [
        f'uuid: {model.uuid}',
        f'area: {model.area.value}',
        f'type: {model.type.value}',
        'tags:' if model.tags else 'tags: []',
        *(f'- {tag}' for tag in model.tags),
        f'date: {model.date}',
        f'updated: {model.updated}',
        'source:' if model.source else 'source: []',
        *(f'- {source}' for source in model.source),
        f'source_type: {model.source_type.value}' if model.source_type.value else 'source_type: ""',
        f'file_type: {model.file_type}',
    ]
    return '\n'.join(lines)


def _parse_document(text: str) -> tuple[dict[str, Any], str]:
    if python_frontmatter is not None:
        post = python_frontmatter.loads(text)
        return dict(post.metadata), str(post.content)

    pattern = re.compile(r'^---\n(?P<meta>.*?)\n---\n?(?P<body>.*)$', re.DOTALL)
    match = pattern.match(text)
    if match is None:
        return {}, text
    raw_meta = yaml.safe_load(match.group('meta'))
    if raw_meta is None:
        raw_meta = {}
    if not isinstance(raw_meta, dict):
        raise ValueError('frontmatter block must deserialize to a mapping')
    return raw_meta, match.group('body')
