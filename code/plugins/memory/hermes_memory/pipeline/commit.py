from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

from filelock import FileLock

from plugins.memory.hermes_memory.backends.lightrag import LightRAGBackend, LightRAGDocument
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.invariant_guard import InvariantGuard
from plugins.memory.hermes_memory.core.models import FrontmatterModel

from .dispatcher import DispatchDecision
from .map import MappedNotionEntry
from .reduce import ReducedEntry


@dataclass(frozen=True, slots=True)
class QuarantineArtifact:
    payload_path: str
    reason_path: str


@dataclass(frozen=True, slots=True)
class CommitResult:
    status: Literal['written', 'updated', 'unchanged', 'dry-run', 'quarantined']
    relative_path: str | None
    reason: str | None
    markdown: str | None
    lightrag_response: Mapping[str, Any] | None
    quarantine: QuarantineArtifact | None


@dataclass(frozen=True, slots=True)
class ExistingDocument:
    relative_path: str
    path: Path
    document: MarkdownDocument


class PipelineCommitter:
    def __init__(
        self,
        *,
        config: ConfigLayer,
        lightrag_backend: LightRAGBackend,
        clock: Clock | None = None,
        invariant_guard: InvariantGuard | None = None,
    ) -> None:
        self._config = config
        self._lightrag_backend = lightrag_backend
        self._clock = clock or SystemClock(config.settings.timezone)
        self._invariant_guard = invariant_guard or InvariantGuard()
        self._codec = FrontmatterCodec(config)

    def locate_existing(
        self,
        source: Sequence[str],
        *,
        vault_root: Path | None = None,
        ignore_relative_paths: Sequence[str] = (),
    ) -> ExistingDocument | None:
        base = self._require_vault_root(vault_root)
        source_set = set(source)
        ignored_paths = {Path(relative_path).as_posix() for relative_path in ignore_relative_paths}
        for relative_path in self._provider_relative_paths(base):
            if relative_path.as_posix() in ignored_paths:
                continue
            path = base / relative_path
            try:
                document = self._codec.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if source_set.intersection(document.frontmatter.source):
                return ExistingDocument(relative_path=relative_path.as_posix(), path=path, document=document)
        return None

    def commit(
        self,
        entry: ReducedEntry,
        dispatch: DispatchDecision,
        *,
        embedding: Sequence[float] | None,
        vault_root: Path | None = None,
        dry_run: bool = False,
        ignore_relative_paths: Sequence[str] = (),
    ) -> CommitResult:
        base = self._require_vault_root(vault_root)
        existing = self.locate_existing(
            entry.frontmatter.source,
            vault_root=base,
            ignore_relative_paths=ignore_relative_paths,
        )
        resolved_entry = entry
        relative_path = dispatch.relative_path
        status: Literal['written', 'updated', 'unchanged', 'dry-run', 'quarantined'] = 'written'
        if existing is not None:
            relative_path = existing.relative_path
            merged_frontmatter = self._merge_frontmatter(existing.document.frontmatter, entry.frontmatter)
            resolved_entry = self._render_entry(entry, frontmatter=merged_frontmatter)
            self._invariant_guard.assert_preserved(existing.document, resolved_entry.document())
            existing_markdown = existing.path.read_text(encoding='utf-8')
            if existing_markdown == resolved_entry.markdown:
                return CommitResult(
                    status='dry-run' if dry_run else 'unchanged',
                    relative_path=relative_path,
                    reason=None,
                    markdown=resolved_entry.markdown,
                    lightrag_response=None,
                    quarantine=None,
                )
            status = 'updated'
        else:
            relative_path = self._resolve_collision(dispatch.relative_path, vault_root=base)

        if dry_run:
            return CommitResult(
                status='dry-run',
                relative_path=relative_path,
                reason=None,
                markdown=resolved_entry.markdown,
                lightrag_response=None,
                quarantine=None,
            )

        target_path = base / relative_path
        self._atomic_write(target_path, resolved_entry.markdown)
        lightrag_response = self._upsert_lightrag(resolved_entry, relative_path=relative_path, embedding=embedding)
        return CommitResult(
            status=status,
            relative_path=relative_path,
            reason=None,
            markdown=resolved_entry.markdown,
            lightrag_response=lightrag_response,
            quarantine=None,
        )

    def quarantine_mapped_entry(
        self,
        mapped: MappedNotionEntry,
        *,
        reason: str,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> CommitResult:
        payload = {
            'datasource': mapped.datasource,
            'source_page_id': mapped.source_page_id,
            'title': mapped.title,
            'source': list(mapped.source),
            'tag_candidates': list(mapped.tag_candidates),
            'chunks': mapped.chunk_payload(),
            'raw_page': mapped.raw_page,
        }
        return self._quarantine_payload(
            title=mapped.logical_basename,
            payload=payload,
            reason=reason,
            vault_root=vault_root,
            dry_run=dry_run,
        )

    def quarantine_reduced_entry(
        self,
        entry: ReducedEntry,
        *,
        reason: str,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> CommitResult:
        payload = {
            'datasource': entry.datasource,
            'source_page_id': entry.source_page_id,
            'title': entry.title,
            'markdown': entry.markdown,
            'raw_page': entry.raw_page,
        }
        return self._quarantine_payload(
            title=entry.title,
            payload=payload,
            reason=reason,
            vault_root=vault_root,
            dry_run=dry_run,
        )

    def _quarantine_payload(
        self,
        *,
        title: str,
        payload: Mapping[str, Any],
        reason: str,
        vault_root: Path | None,
        dry_run: bool,
    ) -> CommitResult:
        base = self._require_vault_root(vault_root)
        bucket = self._config.quarantine_bucket(self._clock.now(), vault_root=base)
        stem = _safe_basename(title)
        payload_path = bucket / f'{stem}.json'
        reason_path = bucket / f'{stem}.reason.txt'
        if not dry_run:
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            reason_path.write_text(reason + '\n', encoding='utf-8')
        return CommitResult(
            status='quarantined',
            relative_path=None,
            reason=reason,
            markdown=None,
            lightrag_response=None,
            quarantine=QuarantineArtifact(
                payload_path=str(payload_path),
                reason_path=str(reason_path),
            ),
        )

    def _render_entry(self, entry: ReducedEntry, *, frontmatter: FrontmatterModel) -> ReducedEntry:
        markdown = self._codec.dumps(MarkdownDocument(frontmatter=frontmatter, body=entry.body))
        return ReducedEntry(
            datasource=entry.datasource,
            source_page_id=entry.source_page_id,
            title=entry.title,
            body=entry.body,
            frontmatter=frontmatter,
            markdown=markdown,
            raw_page=entry.raw_page,
        )

    def _merge_frontmatter(self, existing: FrontmatterModel, candidate: FrontmatterModel) -> FrontmatterModel:
        merged = candidate.ordered_dump()
        merged['uuid'] = existing.uuid
        merged['date'] = existing.date
        merged['source'] = list(existing.source)
        merged['area'] = existing.area.value
        return FrontmatterModel.from_data(merged, tag_registry=self._config.tag_registry)

    def _resolve_collision(self, relative_path: str, *, vault_root: Path) -> str:
        candidate = Path(relative_path)
        if not (vault_root / candidate).exists():
            return candidate.as_posix()
        stem = candidate.stem
        suffix = candidate.suffix
        parent = candidate.parent
        counter = 1
        while True:
            alternative = parent / f'{stem}-{counter}{suffix}'
            if not (vault_root / alternative).exists():
                return alternative.as_posix()
            counter += 1

    def _upsert_lightrag(
        self,
        entry: ReducedEntry,
        *,
        relative_path: str,
        embedding: Sequence[float] | None,
    ) -> Mapping[str, Any]:
        document = LightRAGDocument(
            id=entry.frontmatter.uuid,
            text=entry.markdown,
            embedding=embedding,
            metadata={
                'path': relative_path,
                'file_source': relative_path,
                'title': entry.title,
                'area': entry.frontmatter.area.value,
                'type': entry.frontmatter.type.value,
                'tags': list(entry.frontmatter.tags),
                'source': list(entry.frontmatter.source),
                'datasource': entry.datasource,
                'notion_page_id': entry.source_page_id,
            },
        )
        try:
            return self._lightrag_backend.upsert([document])
        except Exception as exc:
            return {'status': 'failed', 'reason': str(exc)}

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(f'{path}.lock', timeout=self._config.settings.obsidian_writer.filelock_timeout_seconds)
        with lock:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False, prefix=f'.{path.name}.', suffix='.tmp') as handle:
                handle.write(content)
                temp_name = handle.name
            os.replace(temp_name, path)

    def _provider_relative_paths(self, vault_root: Path) -> list[Path]:
        paths: list[Path] = []
        for root_name in self._config.vault_spec.provider_managed_note_roots:
            root = vault_root / root_name.rstrip('/')
            if not root.exists():
                continue
            for path in sorted(root.rglob('*.md')):
                paths.append(path.relative_to(vault_root))
        return paths

    def _require_vault_root(self, vault_root: Path | None) -> Path:
        base = vault_root or self._config.settings.vault_root
        if base is None:
            raise ValueError('vault_root is required for commit operations')
        return base


def _safe_basename(title: str) -> str:
    candidate = title.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'
