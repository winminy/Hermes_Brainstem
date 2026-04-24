from __future__ import annotations

from typing import Protocol

from .models import DownloadedAttachment, NotionAttachment


class AttachmentDownloader(Protocol):
    def download(self, attachment: NotionAttachment) -> DownloadedAttachment:
        ...


class UnsupportedAttachmentDownloader:
    """Guard object for Phase 8 tests; real network downloads are intentionally disabled."""

    def download(self, attachment: NotionAttachment) -> DownloadedAttachment:
        raise RuntimeError(
            'real attachment downloads are disabled in Phase 8; inject a mock AttachmentDownloader '
            f'for {attachment.attachment_id}'
        )
