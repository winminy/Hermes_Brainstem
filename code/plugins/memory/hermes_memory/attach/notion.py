from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .models import NotionAttachment

_ATTACHMENT_BLOCK_TYPES = ('audio', 'file', 'image', 'pdf', 'video')


@dataclass(frozen=True, slots=True)
class NotionAttachmentExtractor:
    def extract(
        self,
        *,
        datasource: str,
        page: Mapping[str, Any],
        blocks: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[NotionAttachment, ...]:
        page_id = _require_string(page.get('id'), field='id')
        page_title = _extract_title(page)
        attachments: list[NotionAttachment] = []
        attachments.extend(_extract_page_property_attachments(datasource=datasource, page=page, page_id=page_id, page_title=page_title))
        attachments.extend(_extract_block_attachments(datasource=datasource, page_id=page_id, page_title=page_title, blocks=blocks))
        return tuple(attachments)


def _extract_page_property_attachments(
    *,
    datasource: str,
    page: Mapping[str, Any],
    page_id: str,
    page_title: str,
) -> list[NotionAttachment]:
    properties = page.get('properties', {})
    if not isinstance(properties, Mapping):
        return []
    attachments: list[NotionAttachment] = []
    for property_name, raw_property in properties.items():
        if not isinstance(raw_property, Mapping):
            continue
        if raw_property.get('type') != 'files':
            continue
        files = raw_property.get('files', [])
        if not isinstance(files, list):
            continue
        for index, item in enumerate(files):
            if not isinstance(item, Mapping):
                continue
            attachment = _parse_file_payload(
                datasource=datasource,
                page_id=page_id,
                page_title=page_title,
                attachment_id=f'property:{property_name}:{index}',
                notion_type='file',
                source_kind='property',
                source_locator=property_name,
                payload=item,
                caption=None,
            )
            if attachment is not None:
                attachments.append(attachment)
    return attachments


def _extract_block_attachments(
    *,
    datasource: str,
    page_id: str,
    page_title: str,
    blocks: Sequence[Mapping[str, Any]],
) -> list[NotionAttachment]:
    attachments: list[NotionAttachment] = []
    for block in blocks:
        block_type = block.get('type')
        if not isinstance(block_type, str) or block_type not in _ATTACHMENT_BLOCK_TYPES:
            continue
        payload = block.get(block_type)
        if not isinstance(payload, Mapping):
            continue
        block_id = _require_string(block.get('id'), field='block.id')
        attachment = _parse_file_payload(
            datasource=datasource,
            page_id=page_id,
            page_title=page_title,
            attachment_id=block_id,
            notion_type=block_type,
            source_kind='block',
            source_locator=block_id,
            payload=payload,
            caption=_caption_text(payload.get('caption')),
        )
        if attachment is not None:
            attachments.append(attachment)
    return attachments


def _parse_file_payload(
    *,
    datasource: str,
    page_id: str,
    page_title: str,
    attachment_id: str,
    notion_type: str,
    source_kind: str,
    source_locator: str,
    payload: Mapping[str, Any],
    caption: str | None,
) -> NotionAttachment | None:
    url, media_type = _extract_url_and_media_type(payload)
    if url is None:
        return None
    filename = _extract_filename(payload, fallback_url=url, attachment_id=attachment_id, notion_type=notion_type, caption=caption)
    return NotionAttachment(
        datasource=datasource,
        page_id=page_id,
        page_title=page_title,
        attachment_id=attachment_id,
        filename=filename,
        download_url=url,
        source_kind=source_kind,
        source_locator=source_locator,
        notion_type=notion_type,
        media_type=media_type,
        caption=caption,
    )


def _extract_url_and_media_type(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for kind in ('file', 'external'):
        nested = payload.get(kind)
        if not isinstance(nested, Mapping):
            continue
        url = nested.get('url')
        if isinstance(url, str) and url.strip():
            media_type = nested.get('media_type')
            return url.strip(), media_type if isinstance(media_type, str) and media_type.strip() else None
    url = payload.get('url')
    if isinstance(url, str) and url.strip():
        media_type = payload.get('media_type')
        return url.strip(), media_type if isinstance(media_type, str) and media_type.strip() else None
    return None, None


def _extract_filename(
    payload: Mapping[str, Any],
    *,
    fallback_url: str,
    attachment_id: str,
    notion_type: str,
    caption: str | None,
) -> str:
    raw_name = payload.get('name')
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    if caption is not None and caption.strip():
        return caption.strip()
    parsed = urlparse(fallback_url)
    candidate = PurePosixPath(parsed.path).name
    if candidate:
        return candidate
    extension = notion_type if notion_type != 'file' else 'bin'
    return f'{attachment_id}.{extension}'


def _caption_text(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        plain_text = item.get('plain_text')
        if isinstance(plain_text, str) and plain_text:
            parts.append(plain_text)
    joined = ''.join(parts).strip()
    return joined or None


def _extract_title(page: Mapping[str, Any]) -> str:
    properties = page.get('properties', {})
    if isinstance(properties, Mapping):
        for value in properties.values():
            if not isinstance(value, Mapping):
                continue
            if value.get('type') != 'title':
                continue
            title = _caption_text(value.get('title'))
            if title:
                return title
    page_id = page.get('id')
    if isinstance(page_id, str) and page_id:
        return page_id
    return 'untitled'


def _require_string(value: object, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f'{field} must be a non-empty string')
