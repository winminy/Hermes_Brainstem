from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re

import yaml

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator

_SOURCE_PREFIX_RE = re.compile(r'^(?P<prefix>[^:]+):')
_FRONTMATTER_RE = re.compile(r'^---\n(?P<meta>.*?)\n---\n?(?P<body>.*)$', re.DOTALL)
_HEADING_RE = re.compile(r'^(?P<indent>\s*)#{3,}\s*(?P<content>.*)$')


@dataclass(frozen=True, slots=True)
class InboxMarkdownArtifact:
    title: str
    logical_path: str
    frontmatter: FrontmatterModel
    body: str
    markdown: str


@dataclass(frozen=True, slots=True)
class AttachmentBinaryArtifact:
    filename: str
    logical_path: str
    payload: bytes
    media_type: str | None
    file_type: str


class ConverterCommon:
    def __init__(
        self,
        config: ConfigLayer,
        *,
        clock: Clock | None = None,
        uuid_generator: UUIDGenerator | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or SystemClock(config.settings.timezone)
        self._uuid_generator = uuid_generator or UUIDGenerator(clock=self._clock)
        self._codec = FrontmatterCodec(config)

    def build_frontmatter(
        self,
        *,
        source: Sequence[str],
        area: str = 'inbox',
        note_type: str = 'memo',
        tags: Sequence[str] = (),
        source_type: str = '',
        file_type: str = 'md',
        uuid: str | None = None,
        date: str | None = None,
        updated: str | None = None,
    ) -> FrontmatterModel:
        today = self._clock.now().date().isoformat()
        normalized_source = tuple(str(item).strip() for item in source if str(item).strip())
        if not normalized_source:
            raise ValueError('converter frontmatter requires at least one source value')
        self._validate_source_prefixes(normalized_source)
        return FrontmatterModel.from_data(
            {
                'uuid': uuid or self._uuid_generator.generate(),
                'area': area,
                'type': note_type,
                'tags': list(tags),
                'date': date or today,
                'updated': updated or today,
                'source': list(normalized_source),
                'source_type': source_type,
                'file_type': file_type,
            },
            tag_registry=self._config.tag_registry,
        )

    def render_note(
        self,
        *,
        title: str,
        body: str,
        source: Sequence[str],
        area: str = 'inbox',
        note_type: str = 'memo',
        tags: Sequence[str] = (),
        source_type: str = '',
        file_type: str = 'md',
        uuid: str | None = None,
        date: str | None = None,
        updated: str | None = None,
    ) -> InboxMarkdownArtifact:
        frontmatter = self.build_frontmatter(
            source=source,
            area=area,
            note_type=note_type,
            tags=tags,
            source_type=source_type,
            file_type=file_type,
            uuid=uuid,
            date=date,
            updated=updated,
        )
        normalized_body = normalize_obsidian_markdown(body)
        document = MarkdownDocument(frontmatter=frontmatter, body=normalized_body)
        markdown = self._codec.dumps(document)
        return InboxMarkdownArtifact(
            title=title.strip() or 'untitled',
            logical_path=f'{frontmatter.area.value}/{safe_basename(title)}.md',
            frontmatter=frontmatter,
            body=normalized_body,
            markdown=markdown,
        )

    def dump_frontmatter_yaml(self, frontmatter: FrontmatterModel) -> str:
        lines = [
            f'uuid: {frontmatter.uuid}',
            f'area: {frontmatter.area.value}',
            f'type: {frontmatter.type.value}',
            'tags:' if frontmatter.tags else 'tags: []',
            *(f'- {tag}' for tag in frontmatter.tags),
            f'date: {frontmatter.date}',
            f'updated: {frontmatter.updated}',
            'source:' if frontmatter.source else 'source: []',
            *(f'- {item}' for item in frontmatter.source),
            f'source_type: {frontmatter.source_type.value}' if frontmatter.source_type.value else 'source_type: ""',
            f'file_type: {frontmatter.file_type}',
        ]
        return '\n'.join(lines)

    def load_frontmatter_yaml(self, text: str) -> FrontmatterModel:
        loaded = yaml.safe_load(text)
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ValueError('frontmatter yaml must deserialize to a mapping')
        return FrontmatterModel.from_data(loaded, tag_registry=self._config.tag_registry)

    def load_document(self, markdown: str) -> MarkdownDocument:
        return self._codec.loads(markdown)

    def attachment_logical_path(self, filename: str) -> str:
        when = self._clock.now()
        relative_root = (
            self._config.vault_spec.attachment_root_template.strip('/')
            .replace('YYYY', when.strftime('%Y'))
            .replace('MM', when.strftime('%m'))
        )
        return f'{relative_root}/{safe_filename(filename)}'

    def build_attachment_artifact(
        self,
        *,
        filename: str,
        payload: bytes,
        media_type: str | None,
    ) -> AttachmentBinaryArtifact:
        return AttachmentBinaryArtifact(
            filename=safe_filename(filename),
            logical_path=self.attachment_logical_path(filename),
            payload=payload,
            media_type=media_type,
            file_type=guess_file_type(filename),
        )

    def _validate_source_prefixes(self, source_values: Sequence[str]) -> None:
        allowed = set(self._config.vault_spec.source_prefixes)
        for value in source_values:
            match = _SOURCE_PREFIX_RE.match(value)
            if match is None:
                raise ValueError(f'invalid source entry: {value}')
            prefix = match.group('prefix')
            if prefix not in allowed:
                raise ValueError(f'unsupported source prefix: {prefix}')


def normalize_obsidian_markdown(body: str) -> str:
    lines: list[str] = []
    in_code_fence = False
    for raw_line in body.splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith('```'):
            in_code_fence = not in_code_fence
            lines.append(raw_line.rstrip())
            continue
        if in_code_fence:
            lines.append(raw_line.rstrip())
            continue
        if stripped.startswith('>'):
            indent = raw_line[: len(raw_line) - len(stripped)]
            content = stripped.lstrip('>').strip()
            lines.append(f'{indent}- {content}' if content else f'{indent}-')
            continue
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match is not None:
            indent = heading_match.group('indent')
            content = heading_match.group('content').strip()
            lines.append(f'{indent}- {content}' if content else f'{indent}-')
            continue
        lines.append(raw_line.rstrip())
    return '\n'.join(lines).strip()


def split_markdown_frontmatter(markdown: str) -> tuple[str | None, str]:
    match = _FRONTMATTER_RE.match(markdown)
    if match is None:
        return None, markdown
    return match.group('meta'), match.group('body')


def safe_basename(title: str) -> str:
    candidate = title.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'


def safe_filename(filename: str) -> str:
    candidate = Path(filename).name.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'attachment.bin'


def guess_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip('.')
    return suffix or 'bin'


__all__ = [
    'AttachmentBinaryArtifact',
    'ConverterCommon',
    'InboxMarkdownArtifact',
    'guess_file_type',
    'normalize_obsidian_markdown',
    'safe_basename',
    'safe_filename',
    'split_markdown_frontmatter',
]
