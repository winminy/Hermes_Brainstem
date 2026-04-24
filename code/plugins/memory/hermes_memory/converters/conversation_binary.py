from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator

from .common import AttachmentBinaryArtifact, ConverterCommon, InboxMarkdownArtifact, safe_filename

_ATTACHMENT_COLLECTION_KEYS = ('attachments', 'files')
_ATTACHMENT_NAME_KEYS = ('filename', 'file_name', 'name')
_ATTACHMENT_MEDIA_KEYS = ('media_type', 'mime_type', 'content_type')
_ATTACHMENT_PAYLOAD_KEYS = ('payload_base64', 'bytes_base64', 'content_base64')


class ConversationBinaryConverter:
    def __init__(
        self,
        config: ConfigLayer,
        *,
        clock: Clock | None = None,
        uuid_generator: UUIDGenerator | None = None,
    ) -> None:
        self._common = ConverterCommon(config, clock=clock, uuid_generator=uuid_generator)

    def convert_session(
        self,
        *,
        session_id: str,
        conversation_history: object,
        title: str | None = None,
        model: str | None = None,
        platform: str | None = None,
        tags: Sequence[str] = (),
        note_type: str = 'memo',
        source: Sequence[str] | None = None,
    ) -> InboxMarkdownArtifact:
        message_count = len(_conversation_messages(conversation_history))
        attachments = self.extract_attachments(session_id=session_id, conversation_history=conversation_history)
        note_title = title or f'Session {session_id}'
        body_lines = [
            f'# {note_title}',
            '',
            '## Session metadata',
            f'- session_id: {session_id}',
            f'- model: {model or ""}',
            f'- platform: {platform or ""}',
            f'- message_count: {message_count}',
            f'- attachment_count: {len(attachments)}',
            '',
            '## Attachments',
        ]
        if attachments:
            for attachment in attachments:
                body_lines.append(f'- ![[{attachment.filename}]]')
        else:
            body_lines.append('- none')
        return self._common.render_note(
            title=note_title,
            body='\n'.join(body_lines),
            source=tuple(source) if source is not None else (f'session:{session_id}',),
            area='inbox',
            note_type=note_type,
            tags=tags,
            source_type='',
            file_type='md',
        )

    def extract_attachments(
        self,
        *,
        session_id: str,
        conversation_history: object,
    ) -> tuple[AttachmentBinaryArtifact, ...]:
        del session_id
        raw_items = _collect_attachment_items(conversation_history)
        artifacts: list[AttachmentBinaryArtifact] = []
        used_names: dict[str, int] = {}
        for raw_item in raw_items:
            filename = _attachment_filename(raw_item)
            if filename is None:
                continue
            unique_name = _unique_filename(filename, used_names)
            payload = _attachment_payload(raw_item)
            media_type = _attachment_media_type(raw_item)
            logical_path = self._attachment_logical_path(unique_name)
            artifacts.append(
                AttachmentBinaryArtifact(
                    filename=unique_name,
                    logical_path=logical_path,
                    payload=payload,
                    media_type=media_type,
                    file_type=Path(unique_name).suffix.lower().lstrip('.') or 'bin',
                )
            )
        return tuple(artifacts)

    def _attachment_logical_path(self, filename: str) -> str:
        return self._common.attachment_logical_path(safe_filename(filename))


def _conversation_messages(conversation_history: object) -> list[Mapping[str, Any]]:
    if isinstance(conversation_history, list):
        return [item for item in conversation_history if isinstance(item, Mapping)]
    if isinstance(conversation_history, Mapping):
        messages = conversation_history.get('messages')
        if isinstance(messages, list):
            return [item for item in messages if isinstance(item, Mapping)]
    return []


def _collect_attachment_items(conversation_history: object) -> list[Mapping[str, Any]]:
    attachments: list[Mapping[str, Any]] = []
    for message in _conversation_messages(conversation_history):
        for key in _ATTACHMENT_COLLECTION_KEYS:
            raw_items = message.get(key)
            if not isinstance(raw_items, list):
                continue
            attachments.extend(item for item in raw_items if isinstance(item, Mapping))
    return attachments


def _attachment_filename(raw_item: Mapping[str, Any]) -> str | None:
    for key in _ATTACHMENT_NAME_KEYS:
        value = raw_item.get(key)
        if isinstance(value, str) and value.strip():
            return safe_filename(value)
    return None


def _attachment_media_type(raw_item: Mapping[str, Any]) -> str | None:
    for key in _ATTACHMENT_MEDIA_KEYS:
        value = raw_item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _attachment_payload(raw_item: Mapping[str, Any]) -> bytes:
    for key in _ATTACHMENT_PAYLOAD_KEYS:
        value = raw_item.get(key)
        if isinstance(value, str) and value.strip():
            return base64.b64decode(value)
    raise ValueError('conversation attachment payload is missing base64 data')


def _unique_filename(filename: str, used_names: dict[str, int]) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    current = used_names.get(filename, 0)
    used_names[filename] = current + 1
    if current == 0:
        return filename
    return f'{stem}-{current}{suffix}'


__all__ = ['ConversationBinaryConverter']
