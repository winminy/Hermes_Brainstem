from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator
from plugins.memory.hermes_memory.pipeline import PersistProcessPipeline

from .classifier import InboxClassification, InboxClassifier
from .dedup import InboxDeduplicator
from .graduator import InboxGraduator


@dataclass(frozen=True, slots=True)
class InboxSourceEntry:
    title: str
    body: str
    source: tuple[str, ...]
    uuid: str | None = None
    source_type: str = ''
    file_type: str = 'md'
    tags: tuple[str, ...] = ()
    note_type: str = 'memo'
    updated: str | None = None
    date: str | None = None


@dataclass(frozen=True, slots=True)
class InboxProcessResult:
    status: str
    inbox_path: str | None
    knowledge_path: str | None
    quarantine_path: str | None
    reason: str | None
    reason_tag: str | None
    queue_path: str | None


@dataclass(frozen=True, slots=True)
class InboxNotionProcessResult:
    status: str
    relative_path: str | None
    quarantine_path: str | None
    reason: str | None
    write_back_response: Mapping[str, Any] | None


class InboxRunner:
    def __init__(
        self,
        config: ConfigLayer,
        *,
        deduplicator: InboxDeduplicator,
        classifier: InboxClassifier,
        graduator: InboxGraduator,
        notion_backend: NotionBackend | None = None,
        pipeline: PersistProcessPipeline | None = None,
        clock: Clock | None = None,
        uuid_generator: UUIDGenerator | None = None,
    ) -> None:
        self._config = config
        self._deduplicator = deduplicator
        self._classifier = classifier
        self._graduator = graduator
        self._notion_backend = notion_backend
        self._pipeline = pipeline
        self._clock = clock or SystemClock(config.settings.timezone)
        self._uuid_generator = uuid_generator or UUIDGenerator(clock=self._clock)
        self._codec = FrontmatterCodec(config)
        self._run_lock = threading.Lock()

    def run(self, entries: list[InboxSourceEntry], *, vault_root: Path, dry_run: bool = False) -> tuple[InboxProcessResult, ...]:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError('parallel inbox processing is not allowed')
        try:
            results: list[InboxProcessResult] = []
            for entry in entries:
                results.append(self.ingest(entry, vault_root=vault_root, dry_run=dry_run))
            return tuple(results)
        finally:
            self._run_lock.release()

    def ingest(self, entry: InboxSourceEntry, *, vault_root: Path, dry_run: bool = False) -> InboxProcessResult:
        inbox_path, document = self._prepare_inbox_entry(entry, vault_root=vault_root, dry_run=dry_run)

        dedup = self._deduplicator.deduplicate(
            entry_path=inbox_path,
            document=document,
            title=entry.title,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        if dedup.action == 'skip':
            return InboxProcessResult(
                status='skipped',
                inbox_path=None if not dry_run else str(inbox_path),
                knowledge_path=None,
                quarantine_path=None,
                reason=dedup.reason,
                reason_tag='source-idempotent',
                queue_path=None,
            )
        if dedup.action == 'updated-existing':
            return InboxProcessResult(
                status='updated-existing',
                inbox_path=None if not dry_run else str(inbox_path),
                knowledge_path=dedup.matched_path,
                quarantine_path=None,
                reason=dedup.reason,
                reason_tag='uuid-collision',
                queue_path=None,
            )
        if dedup.action == 'queued-merge':
            self._annotate_inbox_reason(
                path=inbox_path,
                document=document,
                reason_tag='merge-candidate',
                reason=dedup.reason,
                dry_run=dry_run,
            )
            return InboxProcessResult(
                status='queued-merge',
                inbox_path=str(inbox_path),
                knowledge_path=None,
                quarantine_path=None,
                reason=dedup.reason,
                reason_tag='merge-candidate',
                queue_path=dedup.queue_path,
            )

        classification = self._classifier.classify(title=entry.title, document=document)
        if classification.status == 'success' and classification.area != 'knowledge':
            classification = InboxClassification(
                status='ambiguous',
                title=classification.title,
                body=classification.body,
                area=None,
                note_type=None,
                tags=(),
                reason=f'classifier returned unsupported graduation area: {classification.area}',
                reason_tag='needs-confirmation',
            )

        if classification.status == 'ambiguous':
            self._annotate_inbox_reason(
                path=inbox_path,
                document=document,
                reason_tag=classification.reason_tag or 'needs-confirmation',
                reason=classification.reason,
                dry_run=dry_run,
            )
            return InboxProcessResult(
                status='ambiguous',
                inbox_path=str(inbox_path),
                knowledge_path=None,
                quarantine_path=None,
                reason=classification.reason,
                reason_tag=classification.reason_tag,
                queue_path=None,
            )

        if classification.status == 'invalid':
            quarantine_path = self._move_to_quarantine(
                path=inbox_path,
                reason=classification.reason or 'invalid inbox classification',
                vault_root=vault_root,
                dry_run=dry_run,
            )
            return InboxProcessResult(
                status='quarantined',
                inbox_path=None if not dry_run else str(inbox_path),
                knowledge_path=None,
                quarantine_path=quarantine_path,
                reason=classification.reason,
                reason_tag=classification.reason_tag,
                queue_path=None,
            )

        graduation = self._graduator.graduate(
            entry_path=inbox_path,
            document=document,
            title=entry.title,
            classification=classification,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        return InboxProcessResult(
            status=graduation.status,
            inbox_path=None if not dry_run else str(inbox_path),
            knowledge_path=graduation.knowledge_path,
            quarantine_path=None,
            reason=classification.reason,
            reason_tag=classification.reason_tag,
            queue_path=None,
        )

    def process_notion_page(
        self,
        datasource: str,
        *,
        page_id: str,
        vault_root: Path,
        dry_run: bool = False,
        write_back_properties: Mapping[str, Any] | None = None,
        write_back_children: Sequence[Mapping[str, Any]] = (),
    ) -> InboxNotionProcessResult:
        if self._pipeline is None:
            raise ValueError('InboxRunner.process_notion_page requires a PersistProcessPipeline')
        result = self._pipeline.process_single_entry(
            datasource,
            page_id=page_id,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        write_back_response = self._maybe_write_back_notion(
            page_id=page_id,
            dry_run=dry_run,
            properties=write_back_properties,
            children=write_back_children,
        )
        return InboxNotionProcessResult(
            status=result.status,
            relative_path=result.relative_path,
            quarantine_path=result.quarantine_path,
            reason=result.reason,
            write_back_response=write_back_response,
        )

    def review_existing_entry(
        self,
        entry_path: Path,
        *,
        vault_root: Path,
        dry_run: bool = False,
        notification_reason_tag: str | None = None,
    ) -> InboxProcessResult:
        document = self._codec.loads(entry_path.read_text(encoding='utf-8'))
        title = entry_path.stem
        classification = self._classifier.classify(title=title, document=document)
        if classification.status == 'success' and classification.area != 'knowledge':
            classification = InboxClassification(
                status='ambiguous',
                title=classification.title,
                body=classification.body,
                area=None,
                note_type=None,
                tags=(),
                reason=f'classifier returned unsupported graduation area: {classification.area}',
                reason_tag='needs-confirmation',
            )

        if classification.status == 'ambiguous':
            reason_tag = notification_reason_tag or classification.reason_tag or 'needs-confirmation'
            self._annotate_inbox_reason(
                path=entry_path,
                document=document,
                reason_tag=reason_tag,
                reason=classification.reason,
                dry_run=dry_run,
            )
            return InboxProcessResult(
                status='ambiguous',
                inbox_path=str(entry_path),
                knowledge_path=None,
                quarantine_path=None,
                reason=classification.reason,
                reason_tag=reason_tag,
                queue_path=None,
            )

        if classification.status == 'invalid':
            quarantine_path = self._move_to_quarantine(
                path=entry_path,
                reason=classification.reason or 'invalid inbox classification',
                vault_root=vault_root,
                dry_run=dry_run,
            )
            return InboxProcessResult(
                status='quarantined',
                inbox_path=None if not dry_run else str(entry_path),
                knowledge_path=None,
                quarantine_path=quarantine_path,
                reason=classification.reason,
                reason_tag=classification.reason_tag,
                queue_path=None,
            )

        graduation = self._graduator.graduate(
            entry_path=entry_path,
            document=document,
            title=title,
            classification=classification,
            vault_root=vault_root,
            dry_run=dry_run,
        )
        return InboxProcessResult(
            status=graduation.status,
            inbox_path=None if not dry_run else str(entry_path),
            knowledge_path=graduation.knowledge_path,
            quarantine_path=None,
            reason=classification.reason,
            reason_tag=classification.reason_tag,
            queue_path=None,
        )

    def _prepare_inbox_entry(self, entry: InboxSourceEntry, *, vault_root: Path, dry_run: bool) -> tuple[Path, MarkdownDocument]:
        today = self._clock.now().date().isoformat()
        frontmatter = FrontmatterModel.from_data(
            {
                'uuid': entry.uuid or self._uuid_generator.generate(),
                'area': 'inbox',
                'type': entry.note_type,
                'tags': list(entry.tags),
                'date': entry.date or today,
                'updated': entry.updated or today,
                'source': list(entry.source),
                'source_type': entry.source_type,
                'file_type': entry.file_type,
            },
            tag_registry=self._config.tag_registry,
            allowed_types=self._config.allowed_note_types,
        )
        document = MarkdownDocument(frontmatter=frontmatter, body=entry.body)
        path = self._next_available_path(vault_root / 'inbox', entry.title)
        if not dry_run:
            rendered = self._codec.dumps(document)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding='utf-8')
        return path, document

    def _maybe_write_back_notion(
        self,
        *,
        page_id: str,
        dry_run: bool,
        properties: Mapping[str, Any] | None,
        children: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any] | None:
        if dry_run or (properties is None and not children):
            return None
        if self._notion_backend is None:
            raise ValueError('Notion write-back requested but no NotionBackend is configured')
        return self._notion_backend.write_back_page(page_id, properties=properties, children=children)

    def _annotate_inbox_reason(
        self,
        *,
        path: Path,
        document: MarkdownDocument,
        reason_tag: str,
        reason: str | None,
        dry_run: bool,
    ) -> None:
        state_path = path.with_suffix('.inbox-state.json')
        body = _replace_inbox_status(document.body, reason_tag=reason_tag, reason=reason)
        rendered = self._codec.dumps(MarkdownDocument(frontmatter=document.frontmatter, body=body))
        payload = {'reason_tag': reason_tag, 'reason': reason}
        if not dry_run:
            path.write_text(rendered, encoding='utf-8')
            state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _move_to_quarantine(self, *, path: Path, reason: str, vault_root: Path, dry_run: bool) -> str:
        bucket = self._config.quarantine_bucket(self._clock.now(), vault_root=vault_root)
        target = self._next_available_path(bucket, path.stem)
        reason_path = target.with_suffix(target.suffix + '.reason.txt')
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
            reason_path.write_text(reason + '\n', encoding='utf-8')
        return str(target)

    @staticmethod
    def _next_available_path(root: Path, title: str) -> Path:
        safe_title = _safe_basename(title)
        candidate = root / f'{safe_title}.md'
        if not candidate.exists():
            return candidate
        counter = 1
        while True:
            alternative = root / f'{safe_title}-{counter}.md'
            if not alternative.exists():
                return alternative
            counter += 1


def _replace_inbox_status(body: str, *, reason_tag: str, reason: str | None) -> str:
    replacement_lines = ['## Inbox status', f'- reason_tag: {reason_tag}']
    if reason:
        replacement_lines.append(f'- reason: {reason}')
    replacement = '\n'.join(replacement_lines)
    pattern = re.compile(r'\n?## Inbox status\n(?:- .*\n?)*$', re.MULTILINE)
    trimmed = body.rstrip()
    if pattern.search(trimmed):
        return pattern.sub('\n' + replacement, trimmed).strip()
    if trimmed:
        return trimmed + '\n\n' + replacement
    return replacement


def _safe_basename(title: str) -> str:
    candidate = title.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'
