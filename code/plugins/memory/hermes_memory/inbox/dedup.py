from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from plugins.memory.hermes_memory.backends.lightrag import LightRAGBackend
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest
from plugins.memory.hermes_memory.core.models import FrontmatterModel


DedupAction = Literal['continue', 'skip', 'updated-existing', 'queued-merge']


@dataclass(frozen=True, slots=True)
class MergeCandidate:
    title: str
    path: str
    score: float
    note_type: str


@dataclass(frozen=True, slots=True)
class DedupDecision:
    action: DedupAction
    reason: str | None = None
    matched_path: str | None = None
    source_hash: str | None = None
    merge_candidates: tuple[MergeCandidate, ...] = ()
    queue_path: str | None = None


class InboxDeduplicator:
    def __init__(
        self,
        config: ConfigLayer,
        *,
        lightrag_backend: LightRAGBackend,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._lightrag_backend = lightrag_backend
        self._clock = clock or SystemClock(config.settings.timezone)
        self._codec = FrontmatterCodec(config)

    def deduplicate(
        self,
        *,
        entry_path: Path,
        document: MarkdownDocument,
        title: str,
        vault_root: Path,
        dry_run: bool = False,
    ) -> DedupDecision:
        source_hash = _source_hash(document.frontmatter.source)

        existing_source_match = self._find_source_hash_match(source_hash, current_path=entry_path, vault_root=vault_root)
        if existing_source_match is not None:
            if not dry_run and entry_path.exists():
                entry_path.unlink()
            return DedupDecision(
                action='skip',
                reason='source hash already exists',
                matched_path=existing_source_match,
                source_hash=source_hash,
            )

        existing_uuid_match = self._find_uuid_match(document.frontmatter.uuid, current_path=entry_path, vault_root=vault_root)
        if existing_uuid_match is not None:
            self._update_existing_timestamp(existing_uuid_match, incoming=document, dry_run=dry_run)
            if not dry_run and entry_path.exists():
                entry_path.unlink()
            return DedupDecision(
                action='updated-existing',
                reason='uuid collision updated timestamp only',
                matched_path=str(existing_uuid_match),
                source_hash=source_hash,
            )

        queue_candidates = self._similarity_candidates(title=title, document=document)
        if queue_candidates:
            queue_path = self._queue_merge_hold(
                entry_path=entry_path,
                title=title,
                source_hash=source_hash,
                candidates=queue_candidates,
                vault_root=vault_root,
                dry_run=dry_run,
            )
            return DedupDecision(
                action='queued-merge',
                reason='merge candidate requires user confirmation',
                matched_path=queue_candidates[0].path,
                source_hash=source_hash,
                merge_candidates=tuple(queue_candidates),
                queue_path=queue_path,
            )

        return DedupDecision(action='continue', source_hash=source_hash)

    def _find_source_hash_match(self, source_hash: str, *, current_path: Path, vault_root: Path) -> str | None:
        for path, document in self._iter_note_documents(vault_root):
            if path == current_path:
                continue
            if _source_hash(document.frontmatter.source) == source_hash:
                return str(path)
        quarantine_root = self._config.quarantine_root(vault_root=vault_root)
        if quarantine_root.exists():
            for payload_path in sorted(quarantine_root.rglob('*.json')):
                try:
                    payload = json.loads(payload_path.read_text(encoding='utf-8'))
                except (OSError, ValueError, TypeError):
                    continue
                source = payload.get('source')
                if isinstance(source, list) and _source_hash(tuple(str(item) for item in source)) == source_hash:
                    return str(payload_path)
        return None

    def _find_uuid_match(self, uuid: str, *, current_path: Path, vault_root: Path) -> Path | None:
        for path, document in self._iter_note_documents(vault_root):
            if path == current_path:
                continue
            if document.frontmatter.uuid == uuid:
                return path
        return None

    def _update_existing_timestamp(self, path: Path, *, incoming: MarkdownDocument, dry_run: bool) -> None:
        current = self._codec.loads(path.read_text(encoding='utf-8'))
        new_updated = max(current.frontmatter.updated, incoming.frontmatter.updated)
        if new_updated == current.frontmatter.updated:
            return
        payload = current.frontmatter.ordered_dump()
        payload['updated'] = new_updated
        updated_frontmatter = FrontmatterModel.from_data(payload, tag_registry=self._config.tag_registry)
        rendered = self._codec.dumps(MarkdownDocument(frontmatter=updated_frontmatter, body=current.body))
        if not dry_run:
            path.write_text(rendered, encoding='utf-8')

    def _similarity_candidates(self, *, title: str, document: MarkdownDocument) -> list[MergeCandidate]:
        probe = '\n'.join(part for part in (title, document.body) if part.strip())
        candidates = self._lightrag_backend.query_related(
            probe,
            top_k=self._config.settings.inbox.similarity_top_k,
        )
        results: list[MergeCandidate] = []
        for candidate in candidates:
            if candidate.score < self._config.settings.inbox.similarity_threshold:
                continue
            if candidate.path.startswith('inbox/'):
                continue
            results.append(
                MergeCandidate(
                    title=candidate.title,
                    path=candidate.path,
                    score=candidate.score,
                    note_type=candidate.type,
                )
            )
        return results

    def _queue_merge_hold(
        self,
        *,
        entry_path: Path,
        title: str,
        source_hash: str,
        candidates: Sequence[MergeCandidate],
        vault_root: Path,
        dry_run: bool,
    ) -> str:
        queue_path = vault_root / 'inbox' / self._config.settings.inbox.merge_queue_filename
        record = {
            'queued_at': self._clock.now().isoformat(),
            'entry_path': str(entry_path),
            'title': title,
            'source_hash': source_hash,
            'candidates': [
                {
                    'title': candidate.title,
                    'path': candidate.path,
                    'score': candidate.score,
                    'type': candidate.note_type,
                }
                for candidate in candidates
            ],
        }
        if not dry_run:
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            with queue_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        return str(queue_path)

    def _iter_note_documents(self, vault_root: Path) -> list[tuple[Path, MarkdownDocument]]:
        documents: list[tuple[Path, MarkdownDocument]] = []
        for root_name in self._config.vault_spec.provider_managed_note_roots:
            root = vault_root / root_name.rstrip('/')
            if not root.exists():
                continue
            for path in sorted(root.rglob('*.md')):
                try:
                    document = self._codec.loads(path.read_text(encoding='utf-8'))
                except Exception:
                    continue
                documents.append((path, document))
        quarantine_root = self._config.quarantine_root(vault_root=vault_root)
        if quarantine_root.exists():
            for path in sorted(quarantine_root.rglob('*.md')):
                try:
                    document = self._codec.loads(path.read_text(encoding='utf-8'))
                except Exception:
                    continue
                documents.append((path, document))
        return documents


def _source_hash(source: Sequence[str]) -> str:
    return sha256_hexdigest(json.dumps(list(source), ensure_ascii=False, separators=(',', ':')))
