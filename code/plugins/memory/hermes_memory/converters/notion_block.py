from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from plugins.memory.hermes_memory.backends.notion import _extract_title, _iso_date, _require_string
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator

from .common import ConverterCommon, InboxMarkdownArtifact, normalize_obsidian_markdown, split_markdown_frontmatter

_DEFAULT_ANNOTATIONS: dict[str, bool] = {
    'bold': False,
    'italic': False,
    'strikethrough': False,
    'underline': False,
    'code': False,
}
_TABLE_SEPARATOR_RE = re.compile(r'^\|(?:\s*:?-+:?\s*\|)+$')
_NUMBERED_RE = re.compile(r'^(?P<number>\d+)\.\s+(?P<content>.+)$')
_TODO_RE = re.compile(r'^- \[(?P<done>[ xX])\]\s+(?P<content>.+)$')


class NotionBlockConverter:
    def __init__(
        self,
        config: ConfigLayer,
        *,
        clock: Clock | None = None,
        uuid_generator: UUIDGenerator | None = None,
    ) -> None:
        self._common = ConverterCommon(config, clock=clock, uuid_generator=uuid_generator)

    def convert_page(
        self,
        *,
        page: Mapping[str, Any],
        blocks: Sequence[Mapping[str, Any]],
        title: str | None = None,
        tags: Sequence[str] = (),
        note_type: str = 'memo',
        area: str = 'inbox',
        source: Sequence[str] | None = None,
        children_by_parent: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> InboxMarkdownArtifact:
        page_id = _require_string(page.get('id'), field='id')
        resolved_title = title or _extract_title(page)
        body = self.blocks_to_markdown(
            title=resolved_title,
            page=page,
            blocks=blocks,
            children_by_parent=children_by_parent,
        )
        date = _optional_iso_date(page.get('created_time'))
        updated = _optional_iso_date(page.get('last_edited_time'))
        return self._common.render_note(
            title=resolved_title,
            body=body,
            source=tuple(source) if source is not None else (f'notion:{page_id}',),
            area=area,
            note_type=note_type,
            tags=tags,
            source_type='notion',
            file_type='md',
            date=date,
            updated=updated,
        )

    def blocks_to_markdown(
        self,
        *,
        title: str,
        blocks: Sequence[Mapping[str, Any]],
        page: Mapping[str, Any] | None = None,
        children_by_parent: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> str:
        lines = [f'# {title.strip() or "untitled"}']
        property_lines = self._render_properties(page)
        if property_lines:
            lines.extend(['', '## Notion properties', *property_lines])
        block_lines: list[str] = []
        for block in blocks:
            block_lines.extend(self._render_block(block, children_by_parent=children_by_parent))
        if block_lines:
            lines.extend(['', *block_lines])
        return normalize_obsidian_markdown('\n'.join(lines))

    def document_to_notion_blocks(self, markdown_document: str) -> tuple[dict[str, Any], ...]:
        _, body = split_markdown_frontmatter(markdown_document)
        return self.markdown_to_blocks(body)

    def markdown_to_blocks(self, markdown: str) -> tuple[dict[str, Any], ...]:
        lines = markdown.strip().splitlines()
        blocks: list[dict[str, Any]] = []
        index = 0
        while index < len(lines):
            raw_line = lines[index]
            stripped = raw_line.strip()
            if not stripped:
                index += 1
                continue
            if stripped.startswith('```'):
                language = stripped[3:].strip()
                code_lines: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].strip().startswith('```'):
                    code_lines.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                blocks.append(_code_block('\n'.join(code_lines), language=language))
                continue
            if stripped == '$$':
                equation_lines: list[str] = []
                index += 1
                while index < len(lines) and lines[index].strip() != '$$':
                    equation_lines.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                blocks.append({'type': 'equation', 'equation': {'expression': '\n'.join(equation_lines).strip()}})
                continue
            if _looks_like_table_row(stripped) and index + 1 < len(lines) and _TABLE_SEPARATOR_RE.match(lines[index + 1].strip()):
                table_block, index = _consume_markdown_table(lines, index)
                blocks.append(table_block)
                continue
            if stripped.startswith('# '):
                blocks.append(_rich_text_block('heading_1', stripped[2:].strip()))
                index += 1
                continue
            if stripped.startswith('## '):
                blocks.append(_rich_text_block('heading_2', stripped[3:].strip()))
                index += 1
                continue
            todo_match = _TODO_RE.match(stripped)
            if todo_match is not None:
                blocks.append(
                    {
                        'type': 'to_do',
                        'to_do': {
                            'checked': todo_match.group('done').lower() == 'x',
                            'rich_text': _plain_rich_text(todo_match.group('content').strip()),
                        },
                    }
                )
                index += 1
                continue
            if stripped.startswith('- '):
                blocks.append(_rich_text_block('bulleted_list_item', stripped[2:].strip()))
                index += 1
                continue
            numbered_match = _NUMBERED_RE.match(stripped)
            if numbered_match is not None:
                blocks.append(_rich_text_block('numbered_list_item', numbered_match.group('content').strip()))
                index += 1
                continue
            paragraph_lines = [stripped]
            index += 1
            while index < len(lines):
                candidate = lines[index].strip()
                if not candidate:
                    break
                if candidate.startswith(('```', '# ', '## ', '- ', '$$')):
                    break
                if _NUMBERED_RE.match(candidate) or _TODO_RE.match(candidate):
                    break
                if _looks_like_table_row(candidate):
                    break
                paragraph_lines.append(candidate)
                index += 1
            blocks.append(_rich_text_block('paragraph', ' '.join(paragraph_lines).strip()))
        return tuple(blocks)

    def _render_properties(self, page: Mapping[str, Any] | None) -> list[str]:
        if page is None:
            return []
        properties = page.get('properties', {})
        if not isinstance(properties, Mapping):
            return []
        lines: list[str] = []
        for property_name, raw_property in properties.items():
            if not isinstance(raw_property, Mapping):
                continue
            if raw_property.get('type') == 'title':
                continue
            rendered = self._render_property(raw_property)
            if rendered:
                lines.append(f'- {property_name}: {rendered}')
        url = page.get('url')
        if isinstance(url, str) and url.strip():
            lines.append(f'- notion_url: {url.strip()}')
        return lines

    def _render_property(self, raw_property: Mapping[str, Any]) -> str:
        property_type = raw_property.get('type')
        if property_type in {'title', 'rich_text'}:
            raw_items = raw_property.get(property_type)
            return self._rich_text_to_markdown(raw_items)
        if property_type in {'select', 'status'}:
            value = raw_property.get(property_type)
            if isinstance(value, Mapping):
                name = value.get('name')
                if isinstance(name, str):
                    return name
            return ''
        if property_type == 'multi_select':
            values = raw_property.get('multi_select', [])
            if not isinstance(values, list):
                return ''
            names = [str(value.get('name')) for value in values if isinstance(value, Mapping) and isinstance(value.get('name'), str)]
            return ', '.join(names)
        if property_type == 'date':
            value = raw_property.get('date')
            if not isinstance(value, Mapping):
                return ''
            start = value.get('start')
            end = value.get('end')
            if isinstance(start, str) and isinstance(end, str) and end:
                return f'{start} → {end}'
            return start if isinstance(start, str) else ''
        if property_type == 'checkbox':
            value = raw_property.get('checkbox')
            if isinstance(value, bool):
                return 'true' if value else 'false'
            return ''
        if property_type == 'number':
            value = raw_property.get('number')
            return str(value) if isinstance(value, int | float) else ''
        if property_type in {'email', 'phone_number', 'url'}:
            value = raw_property.get(property_type)
            return value if isinstance(value, str) else ''
        if property_type == 'relation':
            values = raw_property.get('relation', [])
            if not isinstance(values, list):
                return ''
            relation_ids = [str(value.get('id')) for value in values if isinstance(value, Mapping) and isinstance(value.get('id'), str)]
            return ', '.join(relation_ids)
        if property_type == 'formula':
            formula = raw_property.get('formula')
            if not isinstance(formula, Mapping):
                return ''
            for field_name in ('string', 'number', 'boolean'):
                value = formula.get(field_name)
                if value is not None:
                    return str(value)
            return ''
        return ''

    def _render_block(
        self,
        block: Mapping[str, Any],
        *,
        children_by_parent: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> list[str]:
        block_type = block.get('type')
        if not isinstance(block_type, str):
            return []
        block_payload = block.get(block_type)
        if not isinstance(block_payload, Mapping):
            block_payload = {}
        lines: list[str]
        if block_type in {'paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item', 'quote'}:
            text = self._rich_text_to_markdown(block_payload.get('rich_text', []))
            lines = _render_simple_block(block_type, text)
        elif block_type == 'to_do':
            text = self._rich_text_to_markdown(block_payload.get('rich_text', []))
            checked = block_payload.get('checked') is True
            lines = [f'- [{"x" if checked else " "}] {text}'.rstrip()]
        elif block_type == 'callout':
            icon = _render_icon(block_payload.get('icon'))
            text = self._rich_text_to_markdown(block_payload.get('rich_text', []))
            lines = [f'- {icon} {text}'.strip().replace('  ', ' ')]
        elif block_type == 'code':
            language = block_payload.get('language')
            code_text = self._rich_text_plain_text(block_payload.get('rich_text', []))
            fence = f'```{language}'.rstrip() if isinstance(language, str) and language.strip() else '```'
            lines = [fence, code_text, '```']
        elif block_type == 'equation':
            expression = block_payload.get('expression')
            if isinstance(expression, str):
                lines = ['$$', expression, '$$']
            else:
                lines = []
        elif block_type == 'divider':
            lines = ['---']
        elif block_type == 'table':
            lines = self._render_table(block, children_by_parent=children_by_parent)
        elif block_type in {'image', 'file', 'pdf', 'audio', 'video'}:
            filename = _filename_for_media_block(block_type, block_payload)
            lines = [f'![[{filename}]]'] if filename else []
        elif block_type == 'bookmark':
            url = block_payload.get('url')
            lines = [f'- [{url}]({url})'] if isinstance(url, str) and url.strip() else []
        elif block_type == 'child_page':
            title = block_payload.get('title')
            lines = [f'[[{title}]]'] if isinstance(title, str) and title.strip() else []
        else:
            text = self._rich_text_to_markdown(block_payload.get('rich_text', [])) if isinstance(block_payload, Mapping) else ''
            lines = [f'- {text}'.rstrip()] if text else []

        child_lines = self._render_children(block, children_by_parent=children_by_parent)
        if not child_lines:
            return lines
        if block_type in {'bulleted_list_item', 'numbered_list_item', 'to_do', 'toggle'}:
            return lines + _indent_lines(child_lines)
        if lines:
            return lines + [''] + child_lines
        return child_lines

    def _render_children(
        self,
        block: Mapping[str, Any],
        *,
        children_by_parent: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> list[str]:
        children: Sequence[Mapping[str, Any]] = ()
        raw_children = block.get('children')
        if isinstance(raw_children, list):
            children = [child for child in raw_children if isinstance(child, Mapping)]
        if not children:
            block_id = block.get('id')
            if isinstance(block_id, str) and children_by_parent is not None:
                resolved = children_by_parent.get(block_id, ())
                children = [child for child in resolved if isinstance(child, Mapping)]
        rendered: list[str] = []
        for child in children:
            rendered.extend(self._render_block(child, children_by_parent=children_by_parent))
        return rendered

    def _render_table(
        self,
        table_block: Mapping[str, Any],
        *,
        children_by_parent: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> list[str]:
        payload = table_block.get('table')
        if not isinstance(payload, Mapping):
            return []
        raw_rows = table_block.get('children')
        if not isinstance(raw_rows, list):
            block_id = table_block.get('id')
            if isinstance(block_id, str) and children_by_parent is not None:
                raw_rows = list(children_by_parent.get(block_id, ()))
            else:
                return []
        rendered_rows = [
            [self._rich_text_to_markdown(cell) for cell in row.get('table_row', {}).get('cells', []) if isinstance(cell, list)]
            for row in raw_rows
            if isinstance(row, Mapping) and row.get('type') == 'table_row' and isinstance(row.get('table_row'), Mapping)
        ]
        if not rendered_rows:
            return []
        width = max(len(row) for row in rendered_rows)
        normalized_rows = [row + [''] * (width - len(row)) for row in rendered_rows]
        header_row = normalized_rows[0] if payload.get('has_column_header') else [f'Column {index + 1}' for index in range(width)]
        body_rows = normalized_rows[1:] if payload.get('has_column_header') else normalized_rows
        lines = [
            _markdown_table_line(header_row),
            _markdown_table_line(['---'] * width),
            *(_markdown_table_line(row) for row in body_rows),
        ]
        return lines

    def _rich_text_to_markdown(self, raw_items: object) -> str:
        if not isinstance(raw_items, list):
            return ''
        chunks: list[str] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                continue
            chunks.append(self._render_rich_text_item(raw_item))
        return ''.join(chunk for chunk in chunks if chunk)

    def _render_rich_text_item(self, raw_item: Mapping[str, Any]) -> str:
        item_type = raw_item.get('type')
        plain_text = raw_item.get('plain_text')
        content = plain_text if isinstance(plain_text, str) else ''
        if item_type == 'text':
            text_payload = raw_item.get('text')
            if isinstance(text_payload, Mapping):
                nested_content = text_payload.get('content')
                if isinstance(nested_content, str) and nested_content:
                    content = nested_content
                link = text_payload.get('link')
                if isinstance(link, Mapping):
                    url = link.get('url')
                    if isinstance(url, str) and url.strip() and not _looks_like_obsidian_reference(content):
                        content = f'[{content}]({url.strip()})'
        elif item_type == 'mention':
            content = _render_mention(raw_item.get('mention'), plain_text=plain_text)
        elif item_type == 'equation':
            equation = raw_item.get('equation')
            if isinstance(equation, Mapping):
                expression = equation.get('expression')
                if isinstance(expression, str):
                    content = f'${expression}$'
        annotations = raw_item.get('annotations')
        if not isinstance(annotations, Mapping):
            annotations = _DEFAULT_ANNOTATIONS
        return _apply_annotations(content, annotations)

    def _rich_text_plain_text(self, raw_items: object) -> str:
        if not isinstance(raw_items, list):
            return ''
        chunks: list[str] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                continue
            plain_text = raw_item.get('plain_text')
            if isinstance(plain_text, str):
                chunks.append(plain_text)
        return ''.join(chunks)


def _optional_iso_date(value: object) -> str | None:
    if value is None:
        return None
    return _iso_date(value)


def _render_simple_block(block_type: str, text: str) -> list[str]:
    if block_type == 'paragraph':
        return [text] if text else []
    if block_type == 'heading_1':
        return [f'# {text}'.rstrip()] if text else []
    if block_type == 'heading_2':
        return [f'## {text}'.rstrip()] if text else []
    if block_type in {'heading_3', 'quote'}:
        return [f'- {text}'.rstrip()] if text else ['-']
    if block_type == 'bulleted_list_item':
        return [f'- {text}'.rstrip()] if text else ['-']
    if block_type == 'numbered_list_item':
        return [f'1. {text}'.rstrip()] if text else ['1.']
    return []


def _apply_annotations(content: str, annotations: Mapping[str, Any]) -> str:
    if not content:
        return ''
    rendered = content
    if annotations.get('code') is True:
        return f'`{rendered}`'
    if annotations.get('bold') is True:
        rendered = f'**{rendered}**'
    if annotations.get('italic') is True:
        rendered = f'*{rendered}*'
    if annotations.get('strikethrough') is True:
        rendered = f'~~{rendered}~~'
    return rendered


def _render_mention(raw_mention: object, *, plain_text: object) -> str:
    if not isinstance(raw_mention, Mapping):
        return plain_text if isinstance(plain_text, str) else ''
    mention_type = raw_mention.get('type')
    if mention_type in {'page', 'database'}:
        label = plain_text if isinstance(plain_text, str) and plain_text else 'untitled'
        return label if _looks_like_obsidian_reference(label) else f'[[{label}]]'
    if mention_type == 'date':
        date_payload = raw_mention.get('date')
        if isinstance(date_payload, Mapping):
            start = date_payload.get('start')
            end = date_payload.get('end')
            if isinstance(start, str) and isinstance(end, str) and end:
                return f'{start} → {end}'
            if isinstance(start, str):
                return start
    if mention_type == 'user':
        user_payload = raw_mention.get('user')
        if isinstance(user_payload, Mapping):
            name = user_payload.get('name')
            if isinstance(name, str) and name.strip():
                return f'@{name.strip()}'
    return plain_text if isinstance(plain_text, str) else ''


def _render_icon(raw_icon: object) -> str:
    if not isinstance(raw_icon, Mapping):
        return ''
    if raw_icon.get('type') == 'emoji':
        emoji = raw_icon.get('emoji')
        return emoji if isinstance(emoji, str) else ''
    return ''


def _filename_for_media_block(block_type: str, payload: Mapping[str, Any]) -> str | None:
    caption = payload.get('caption')
    if isinstance(caption, list):
        caption_text = ''.join(
            item.get('plain_text', '')
            for item in caption
            if isinstance(item, Mapping) and isinstance(item.get('plain_text'), str)
        ).strip()
        if caption_text:
            return caption_text
    media_value = payload.get(block_type)
    if isinstance(media_value, Mapping):
        nested = media_value.get(media_value.get('type', ''))
        if isinstance(nested, Mapping):
            url = nested.get('url')
            if isinstance(url, str) and url.strip():
                parsed = urlparse(url)
                return Path(parsed.path).name or None
    url = payload.get('url')
    if isinstance(url, str) and url.strip():
        parsed = urlparse(url)
        return Path(parsed.path).name or None
    return None


def _indent_lines(lines: Sequence[str]) -> list[str]:
    return [f'  {line}' if line else '' for line in lines]


def _looks_like_obsidian_reference(value: str) -> bool:
    return value.startswith('[[') or value.startswith('![[')


def _plain_rich_text(content: str) -> list[dict[str, Any]]:
    return [
        {
            'type': 'text',
            'text': {'content': content, 'link': None},
            'plain_text': content,
            'annotations': dict(_DEFAULT_ANNOTATIONS),
        }
    ]


def _rich_text_block(block_type: str, content: str) -> dict[str, Any]:
    return {'type': block_type, block_type: {'rich_text': _plain_rich_text(content)}}


def _code_block(code: str, *, language: str) -> dict[str, Any]:
    return {
        'type': 'code',
        'code': {
            'language': language,
            'rich_text': _plain_rich_text(code),
        },
    }


def _looks_like_table_row(line: str) -> bool:
    return line.startswith('|') and line.endswith('|') and line.count('|') >= 2


def _consume_markdown_table(lines: Sequence[str], start_index: int) -> tuple[dict[str, Any], int]:
    table_lines: list[str] = []
    index = start_index
    while index < len(lines) and _looks_like_table_row(lines[index].strip()):
        table_lines.append(lines[index].strip())
        index += 1
    header = _split_markdown_table_row(table_lines[0])
    body_lines = table_lines[2:] if len(table_lines) >= 2 else []
    rows = [header, *(_split_markdown_table_row(row) for row in body_lines)]
    children = [
        {
            'type': 'table_row',
            'table_row': {
                'cells': [_plain_rich_text(cell) for cell in row],
            },
        }
        for row in rows
    ]
    table_block = {
        'type': 'table',
        'table': {
            'table_width': len(header),
            'has_column_header': True,
            'has_row_header': False,
        },
        'children': children,
    }
    return table_block, index


def _split_markdown_table_row(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip('|').split('|')]
    return cells


def _markdown_table_line(cells: Sequence[str]) -> str:
    escaped = [cell.replace('|', '\\|').replace('\n', ' ') for cell in cells]
    return '| ' + ' | '.join(escaped) + ' |'


__all__ = ['NotionBlockConverter']
