from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


AttachmentScope = Literal['knowledge', 'skill']


@dataclass(frozen=True, slots=True)
class NotionAttachment:
    datasource: str
    page_id: str
    page_title: str
    attachment_id: str
    filename: str
    download_url: str
    source_kind: str
    source_locator: str
    notion_type: str
    media_type: str | None = None
    caption: str | None = None

    @property
    def extension(self) -> str:
        suffix = Path(self.filename).suffix.lower().lstrip('.')
        return suffix or _default_extension(self.notion_type)

    @property
    def stem(self) -> str:
        return Path(self.filename).stem or self.attachment_id

    @property
    def is_markdown(self) -> bool:
        return self.extension in {'md', 'markdown'}

    @property
    def is_image(self) -> bool:
        return self.extension in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


@dataclass(frozen=True, slots=True)
class DownloadedAttachment:
    payload: bytes
    media_type: str | None = None
    charset: str = 'utf-8'


@dataclass(frozen=True, slots=True)
class AttachResult:
    page_id: str
    attachment_id: str
    filename: str
    scope: AttachmentScope
    status: str
    raw_path: str | None
    note_path: str | None
    manifest_path: str | None
    sha256: str
    saved_path_message: str


@dataclass(frozen=True, slots=True)
class AttachBatchResult:
    datasource: str
    page_id: str
    page_title: str
    scope: AttachmentScope
    results: tuple[AttachResult, ...]


def _default_extension(notion_type: str) -> str:
    if notion_type == 'pdf':
        return 'pdf'
    if notion_type == 'image':
        return 'png'
    if notion_type == 'audio':
        return 'mp3'
    if notion_type == 'video':
        return 'mp4'
    if notion_type == 'file':
        return 'bin'
    return 'bin'
