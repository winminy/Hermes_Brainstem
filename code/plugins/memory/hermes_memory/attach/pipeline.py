from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Protocol

import yaml

from plugins.memory.hermes_memory.attach.downloader import AttachmentDownloader, UnsupportedAttachmentDownloader
from plugins.memory.hermes_memory.attach.models import (
    AttachBatchResult,
    AttachResult,
    AttachmentScope,
    DownloadedAttachment,
    NotionAttachment,
)
from plugins.memory.hermes_memory.attach.notion import NotionAttachmentExtractor
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator
from plugins.memory.hermes_memory.inbox.runner import InboxProcessResult, InboxSourceEntry


@dataclass(frozen=True, slots=True)
class AttachPolicy:
    allowed_scopes: tuple[str, ...]
    source_prefix: str


@dataclass(frozen=True, slots=True)
class RawPlacement:
    status: str
    path: Path
    manifest_path: Path
    relative_path: str


class InboxRunnerProtocol(Protocol):
    def ingest(
        self,
        entry: InboxSourceEntry,
        *,
        vault_root: Path,
        dry_run: bool = False,
    ) -> InboxProcessResult:
        ...


class PersistAttachPipeline:
    def __init__(
        self,
        *,
        config: ConfigLayer,
        downloader: AttachmentDownloader | None = None,
        notion_backend: NotionBackend | None = None,
        inbox_runner: InboxRunnerProtocol | None = None,
        extractor: NotionAttachmentExtractor | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._downloader = downloader or UnsupportedAttachmentDownloader()
        self._notion_backend = notion_backend
        self._inbox_runner = inbox_runner
        self._extractor = extractor or NotionAttachmentExtractor()
        self._clock = clock or SystemClock(config.settings.timezone)
        self._policy = self._load_policy()
        self._allowed_skill_names = self._load_skill_registry()
        self._codec = FrontmatterCodec(config)
        self._uuid_generator = UUIDGenerator(clock=self._clock)

    def process_notion_page(
        self,
        datasource: str,
        *,
        page_id: str | None = None,
        page: Mapping[str, Any] | None = None,
        blocks: Sequence[Mapping[str, Any]] | None = None,
        scope: AttachmentScope = 'knowledge',
        skill_name: str | None = None,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> AttachBatchResult:
        if page is None:
            if page_id is None:
                raise ValueError('page or page_id is required for persist.attach')
            if self._notion_backend is None:
                raise ValueError('NotionBackend is required when page is not provided')
            page = self._notion_backend.retrieve_page(page_id)
        resolved_page_id = _require_string(page.get('id'), field='page.id')
        if blocks is None:
            if self._notion_backend is None:
                blocks = ()
            else:
                blocks = self._notion_backend.list_block_children(resolved_page_id)
        attachments = self._extractor.extract(datasource=datasource, page=page, blocks=blocks)
        results = [
            self.persist_attachment(
                attachment,
                scope=scope,
                skill_name=skill_name,
                vault_root=vault_root,
                dry_run=dry_run,
            )
            for attachment in attachments
        ]
        return AttachBatchResult(
            datasource=datasource,
            page_id=resolved_page_id,
            page_title=_extract_title(page),
            scope=scope,
            results=tuple(results),
        )

    def persist_attachment(
        self,
        attachment: NotionAttachment,
        *,
        scope: AttachmentScope = 'knowledge',
        skill_name: str | None = None,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> AttachResult:
        self._validate_scope(scope)
        resolved_skill = self._validate_skill_name(scope=scope, skill_name=skill_name)
        downloaded = self._downloader.download(attachment)
        content_hash = sha256_hexdigest(downloaded.payload)
        source_value = self._source_value(attachment=attachment, content_hash=content_hash)
        if attachment.is_markdown:
            return self._persist_markdown_attachment(
                attachment,
                downloaded=downloaded,
                source_value=source_value,
                content_hash=content_hash,
                scope=scope,
                skill_name=resolved_skill,
                vault_root=vault_root,
                dry_run=dry_run,
            )
        return self._persist_binary_attachment(
            attachment,
            downloaded=downloaded,
            source_value=source_value,
            content_hash=content_hash,
            scope=scope,
            skill_name=resolved_skill,
            vault_root=vault_root,
            dry_run=dry_run,
        )

    def _persist_markdown_attachment(
        self,
        attachment: NotionAttachment,
        *,
        downloaded: DownloadedAttachment,
        source_value: str,
        content_hash: str,
        scope: AttachmentScope,
        skill_name: str | None,
        vault_root: Path | None,
        dry_run: bool,
    ) -> AttachResult:
        body = _decode_markdown(downloaded, filename=attachment.filename)
        decorated_body = self._render_markdown_body(
            attachment=attachment,
            body=body,
            content_hash=content_hash,
            scope=scope,
        )
        title = self._note_title(attachment)
        if scope == 'knowledge':
            inbox_result = self._require_inbox_runner().ingest(
                InboxSourceEntry(
                    title=title,
                    body=decorated_body,
                    source=(source_value,),
                    source_type='notion',
                    file_type='md',
                ),
                vault_root=self._require_vault_root(vault_root),
                dry_run=dry_run,
            )
            note_path = inbox_result.knowledge_path or inbox_result.inbox_path
            status = 'deduplicated' if inbox_result.status in {'skipped', 'updated-existing'} else inbox_result.status
            saved_path_message = self._knowledge_saved_message(note_path=note_path, raw_path=None)
            return AttachResult(
                page_id=attachment.page_id,
                attachment_id=attachment.attachment_id,
                filename=attachment.filename,
                scope=scope,
                status=status,
                raw_path=None,
                note_path=note_path,
                manifest_path=None,
                sha256=content_hash,
                saved_path_message=saved_path_message,
            )

        note_path = self._write_reference_note(
            attachment=attachment,
            body=decorated_body,
            source_value=source_value,
            file_type='md',
            skill_name=skill_name,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        saved_path_message = self._skill_saved_message(raw_path=None, note_path=note_path)
        return AttachResult(
            page_id=attachment.page_id,
            attachment_id=attachment.attachment_id,
            filename=attachment.filename,
            scope=scope,
            status='written' if not dry_run else 'dry-run',
            raw_path=None,
            note_path=note_path,
            manifest_path=None,
            sha256=content_hash,
            saved_path_message=saved_path_message,
        )

    def _persist_binary_attachment(
        self,
        attachment: NotionAttachment,
        *,
        downloaded: DownloadedAttachment,
        source_value: str,
        content_hash: str,
        scope: AttachmentScope,
        skill_name: str | None,
        vault_root: Path | None,
        dry_run: bool,
    ) -> AttachResult:
        raw_placement = self._place_binary(
            attachment=attachment,
            downloaded=downloaded,
            source_value=source_value,
            content_hash=content_hash,
            scope=scope,
            skill_name=skill_name,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        raw_reference = Path(raw_placement.relative_path).name
        body = self._render_binary_companion_body(
            attachment=attachment,
            raw_reference=raw_reference,
            raw_relative_path=raw_placement.relative_path,
            content_hash=content_hash,
            scope=scope,
        )
        if scope == 'knowledge':
            inbox_result = self._require_inbox_runner().ingest(
                InboxSourceEntry(
                    title=self._note_title(attachment),
                    body=body,
                    source=(source_value,),
                    source_type='notion',
                    file_type=attachment.extension,
                ),
                vault_root=self._require_vault_root(vault_root),
                dry_run=dry_run,
            )
            note_path = inbox_result.knowledge_path or inbox_result.inbox_path
            status = 'deduplicated' if raw_placement.status == 'deduplicated' or inbox_result.status in {'skipped', 'updated-existing'} else inbox_result.status
            saved_path_message = self._knowledge_saved_message(note_path=note_path, raw_path=raw_placement.relative_path)
            return AttachResult(
                page_id=attachment.page_id,
                attachment_id=attachment.attachment_id,
                filename=attachment.filename,
                scope=scope,
                status=status,
                raw_path=raw_placement.relative_path,
                note_path=note_path,
                manifest_path=str(raw_placement.manifest_path),
                sha256=content_hash,
                saved_path_message=saved_path_message,
            )

        note_path = self._write_reference_note(
            attachment=attachment,
            body=body,
            source_value=source_value,
            file_type=attachment.extension,
            skill_name=skill_name,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        status = 'deduplicated' if raw_placement.status == 'deduplicated' else ('dry-run' if dry_run else 'written')
        saved_path_message = self._skill_saved_message(raw_path=raw_placement.relative_path, note_path=note_path)
        return AttachResult(
            page_id=attachment.page_id,
            attachment_id=attachment.attachment_id,
            filename=attachment.filename,
            scope=scope,
            status=status,
            raw_path=raw_placement.relative_path,
            note_path=note_path,
            manifest_path=str(raw_placement.manifest_path),
            sha256=content_hash,
            saved_path_message=saved_path_message,
        )

    def _place_binary(
        self,
        *,
        attachment: NotionAttachment,
        downloaded: DownloadedAttachment,
        source_value: str,
        content_hash: str,
        scope: AttachmentScope,
        skill_name: str | None,
        vault_root: Path | None,
        dry_run: bool,
    ) -> RawPlacement:
        root = self._binary_root(scope=scope, skill_name=skill_name, vault_root=vault_root)
        search_root = self._binary_search_root(
            scope=scope,
            skill_name=skill_name,
            vault_root=vault_root,
        )
        existing = self._find_existing_binary(root=search_root, content_hash=content_hash)
        if existing is not None:
            return existing
        target = self._next_available_path(root, attachment.filename)
        manifest_path = target.with_suffix(target.suffix + '.attach.json')
        relative_path = self._display_path(path=target, scope=scope, vault_root=vault_root)
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(downloaded.payload)
            manifest_path.write_text(
                json.dumps(
                    {
                        'sha256': content_hash,
                        'source': source_value,
                        'scope': scope,
                        'attachment_id': attachment.attachment_id,
                        'page_id': attachment.page_id,
                        'filename': attachment.filename,
                        'stored_path': relative_path,
                        'media_type': downloaded.media_type or attachment.media_type,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
        return RawPlacement(
            status='dry-run' if dry_run else 'written',
            path=target,
            manifest_path=manifest_path,
            relative_path=relative_path,
        )

    def _write_reference_note(
        self,
        *,
        attachment: NotionAttachment,
        body: str,
        source_value: str,
        file_type: str,
        skill_name: str | None,
        vault_root: Path | None,
        dry_run: bool,
    ) -> str:
        root = self._skill_references_root(skill_name=skill_name, vault_root=vault_root)
        existing = self._find_existing_note(root=root, source_value=source_value)
        if existing is not None:
            return str(existing)
        note_path = self._next_available_path(root, self._note_filename(attachment))
        document = MarkdownDocument(
            frontmatter=self._frontmatter(source_value=source_value, file_type=file_type),
            body=body,
        )
        rendered = self._codec.dumps(document)
        if not dry_run:
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(rendered, encoding='utf-8')
        return str(note_path)

    def _render_markdown_body(
        self,
        *,
        attachment: NotionAttachment,
        body: str,
        content_hash: str,
        scope: AttachmentScope,
    ) -> str:
        trimmed = body.rstrip()
        metadata = [
            '## Attachment metadata',
            f'- page_id: {attachment.page_id}',
            f'- attachment_id: {attachment.attachment_id}',
            f'- filename: {attachment.filename}',
            f'- sha256: {content_hash}',
            f'- scope: {scope}',
        ]
        if trimmed:
            return trimmed + '\n\n' + '\n'.join(metadata)
        return '\n'.join([f'# {self._note_title(attachment)}', ''] + metadata)

    def _render_binary_companion_body(
        self,
        *,
        attachment: NotionAttachment,
        raw_reference: str,
        raw_relative_path: str,
        content_hash: str,
        scope: AttachmentScope,
    ) -> str:
        return '\n'.join(
            [
                f'# {self._note_title(attachment)}',
                '',
                '## Attachment',
                f'- page_id: {attachment.page_id}',
                f'- attachment_id: {attachment.attachment_id}',
                f'- filename: {attachment.filename}',
                f'- stored_path: {raw_relative_path}',
                f'- sha256: {content_hash}',
                f'- scope: {scope}',
                '',
                '## Embedded file',
                f'![[{raw_reference}]]',
            ]
        )

    def _frontmatter(self, *, source_value: str, file_type: str) -> FrontmatterModel:
        today = self._clock.now().date().isoformat()
        payload: dict[str, object] = {
            'uuid': self._uuid_generator.generate(),
            'area': 'knowledge',
            'type': 'memo',
            'tags': [],
            'date': today,
            'updated': today,
            'source': [source_value],
            'source_type': 'notion',
            'file_type': file_type,
        }
        return FrontmatterModel.from_data(payload, tag_registry=self._config.tag_registry)

    def _source_value(self, *, attachment: NotionAttachment, content_hash: str) -> str:
        return (
            f'{self._policy.source_prefix}notion:{attachment.page_id}:{attachment.attachment_id}:'
            f'{content_hash}'
        )

    def _validate_scope(self, scope: AttachmentScope) -> None:
        if scope not in self._policy.allowed_scopes:
            raise ValueError(f'unsupported persist.attach scope: {scope}')

    def _validate_skill_name(self, *, scope: AttachmentScope, skill_name: str | None) -> str | None:
        if scope != 'skill':
            return None
        if skill_name is None or not skill_name.strip():
            raise ValueError('scope=skill requires skill_name')
        resolved = skill_name.strip()
        if resolved not in self._allowed_skill_names:
            raise ValueError(f'skill_name is not registered in skill_registry.md: {resolved}')
        return resolved

    def _load_policy(self) -> AttachPolicy:
        markdown = self._config.resources.read_text(
            f'{self._config.settings.resource_system_root}/self_reference/persist_policy.md'
        )
        block = _extract_fenced_yaml(markdown)
        match = re.search(r'persist\.attach:\n(?P<body>(?:\s{4}.+\n?)+)', block)
        if match is None:
            raise ValueError('persist.attach policy block is required')
        body = match.group('body')
        scopes_match = re.search(r'allowed_scopes:\s*\[(?P<value>[^\]]+)\]', body)
        prefix_match = re.search(r'source_prefix:\s*(?P<value>[^\n]+)', body)
        if scopes_match is None or prefix_match is None:
            raise ValueError('persist.attach allowed_scopes and source_prefix are required')
        scopes = tuple(
            item.strip().strip('"').strip("'")
            for item in scopes_match.group('value').split(',')
            if item.strip()
        )
        source_prefix = prefix_match.group('value').strip().strip('"').strip("'")
        return AttachPolicy(allowed_scopes=scopes, source_prefix=source_prefix)

    def _load_skill_registry(self) -> tuple[str, ...]:
        markdown = self._config.resources.read_text(f'{self._config.settings.resource_system_root}/skills/skill_registry.md')
        loaded = yaml.safe_load(_extract_fenced_yaml(markdown))
        if not isinstance(loaded, Mapping):
            raise ValueError('skill_registry.md must deserialize to a mapping')
        default_skills = loaded.get('default_skills')
        if not isinstance(default_skills, list):
            raise ValueError('skill_registry.md must define default_skills')
        names: list[str] = []
        for item in default_skills:
            if not isinstance(item, Mapping):
                continue
            raw_id = item.get('id')
            if isinstance(raw_id, str) and raw_id.strip():
                names.append(raw_id.strip())
        return tuple(names)

    def _binary_root(self, *, scope: AttachmentScope, skill_name: str | None, vault_root: Path | None) -> Path:
        if scope == 'knowledge':
            return self._config.attachment_bucket(
                self._clock.now(),
                vault_root=self._require_vault_root(vault_root),
            )
        return self._skill_references_root(skill_name=skill_name, vault_root=vault_root)

    def _binary_search_root(
        self,
        *,
        scope: AttachmentScope,
        skill_name: str | None,
        vault_root: Path | None,
    ) -> Path:
        if scope == 'knowledge':
            attachment_root = self._config.vault_spec.attachment_root_template.strip('/').split('/', 1)[0]
            return self._require_vault_root(vault_root) / attachment_root
        return self._skill_references_root(skill_name=skill_name, vault_root=vault_root)

    def _skill_references_root(self, *, skill_name: str | None, vault_root: Path | None) -> Path:
        del vault_root
        if skill_name is None:
            raise ValueError('skill_name is required to resolve skill references path')
        return self._config.skill_root() / skill_name / 'references'

    def _find_existing_note(self, *, root: Path, source_value: str) -> Path | None:
        if not root.exists():
            return None
        for path in sorted(root.rglob('*.md')):
            try:
                document = self._codec.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if source_value in document.frontmatter.source:
                return path
        return None

    def _find_existing_binary(self, *, root: Path, content_hash: str) -> RawPlacement | None:
        if not root.exists():
            return None
        for manifest_path in sorted(root.rglob('*.attach.json')):
            try:
                payload = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                continue
            manifest_hash = payload.get('sha256')
            stored_path = payload.get('stored_path')
            if manifest_hash != content_hash or not isinstance(stored_path, str):
                continue
            raw_path = Path(str(manifest_path).removesuffix('.attach.json'))
            return RawPlacement(
                status='deduplicated',
                path=raw_path,
                manifest_path=manifest_path,
                relative_path=stored_path,
            )
        return None

    @staticmethod
    def _note_filename(attachment: NotionAttachment) -> str:
        if attachment.is_markdown:
            return attachment.filename
        return f'{_safe_basename(attachment.page_title)} - {_safe_basename(attachment.stem)}.md'

    @staticmethod
    def _note_title(attachment: NotionAttachment) -> str:
        page_title = attachment.page_title.strip()
        file_title = attachment.stem.strip()
        if not page_title or page_title == file_title:
            return file_title or attachment.filename
        return f'{page_title} - {file_title}'

    @staticmethod
    def _next_available_path(root: Path, filename: str) -> Path:
        candidate_name = _safe_filename(filename)
        candidate = root / candidate_name
        if not candidate.exists():
            return candidate
        stem = Path(candidate_name).stem
        suffix = Path(candidate_name).suffix
        counter = 1
        while True:
            alternative = root / f'{stem}-{counter}{suffix}'
            if not alternative.exists():
                return alternative
            counter += 1

    def _display_path(self, *, path: Path, scope: AttachmentScope, vault_root: Path | None) -> str:
        if scope == 'knowledge':
            base = self._require_vault_root(vault_root)
            return path.relative_to(base).as_posix()
        return str(path)

    def _knowledge_saved_message(self, *, note_path: str | None, raw_path: str | None) -> str:
        parts = ['persist.attach saved to knowledge scope']
        if raw_path is not None:
            parts.append(f'raw={raw_path}')
        if note_path is not None:
            parts.append(f'note={note_path}')
        return '; '.join(parts)

    def _skill_saved_message(self, *, raw_path: str | None, note_path: str | None) -> str:
        parts = ['persist.attach saved to skill scope']
        if raw_path is not None:
            parts.append(f'raw={raw_path}')
        if note_path is not None:
            parts.append(f'note={note_path}')
        return '; '.join(parts)

    def _require_vault_root(self, vault_root: Path | None) -> Path:
        base = vault_root or self._config.settings.vault_root
        if base is None:
            raise ValueError('vault_root is required for knowledge-scope attachments')
        return base

    def _require_inbox_runner(self) -> InboxRunnerProtocol:
        if self._inbox_runner is None:
            raise ValueError('scope=knowledge requires an InboxRunner')
        return self._inbox_runner


def _extract_title(page: Mapping[str, Any]) -> str:
    properties = page.get('properties', {})
    if isinstance(properties, Mapping):
        for value in properties.values():
            if not isinstance(value, Mapping):
                continue
            if value.get('type') != 'title':
                continue
            title = _plain_text(value.get('title'))
            if title:
                return title
    page_id = page.get('id')
    if isinstance(page_id, str) and page_id:
        return page_id
    return 'untitled'


def _plain_text(value: object) -> str:
    if not isinstance(value, list):
        return ''
    parts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        plain_text = item.get('plain_text')
        if isinstance(plain_text, str):
            parts.append(plain_text)
    return ''.join(parts).strip()


def _decode_markdown(downloaded: DownloadedAttachment, *, filename: str) -> str:
    try:
        return downloaded.payload.decode(downloaded.charset)
    except UnicodeDecodeError as exc:
        raise ValueError(f'markdown attachment is not decodable: {filename}') from exc


def _extract_fenced_yaml(markdown: str) -> str:
    match = re.search(r'```yaml\n(?P<body>.*?)\n```', markdown, re.DOTALL)
    if match is None:
        raise ValueError('yaml fenced block not found')
    return match.group('body')


def _require_string(value: object, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f'{field} must be a non-empty string')


def _safe_basename(value: str) -> str:
    candidate = value.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'


def _safe_filename(filename: str) -> str:
    path = Path(filename)
    stem = _safe_basename(path.stem)
    suffix = path.suffix.lower()
    return f'{stem}{suffix}' if suffix else stem
