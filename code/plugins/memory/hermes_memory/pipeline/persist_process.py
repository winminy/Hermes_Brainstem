from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugins.memory.hermes_memory.backends.embedding import EmbeddingBackend, build_embedding_backend
from plugins.memory.hermes_memory.backends.lightrag import LightRAGBackend, LightRAGHTTPBackend
from plugins.memory.hermes_memory.backends.notion import NotionBackend, _require_string
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.logger import configure_logging

from .commit import CommitResult, PipelineCommitter
from .dispatcher import PipelineDispatcher
from .map import MappedNotionEntry, SkipEntryError, SourceMapper
from .reduce import ReducedEntry, StructuredEntryReducer


@dataclass(frozen=True, slots=True)
class SyncEntryResult:
    datasource: str
    source_page_id: str
    status: str
    relative_path: str | None
    reason: str | None
    quarantine_path: str | None
    markdown: str | None


@dataclass(frozen=True, slots=True)
class SyncBatchResult:
    mode: str
    datasources: tuple[str, ...]
    entries: tuple[SyncEntryResult, ...]
    counts: Mapping[str, int]


class PersistProcessPipeline:
    def __init__(
        self,
        *,
        config: ConfigLayer,
        notion_backend: NotionBackend | None = None,
        mapper: SourceMapper | None = None,
        reducer: StructuredEntryReducer | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        lightrag_backend: LightRAGBackend | None = None,
        dispatcher: PipelineDispatcher | None = None,
        committer: PipelineCommitter | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or SystemClock(config.settings.timezone)
        self._notion_backend = notion_backend or NotionBackend(config=config)
        self._mapper = mapper or SourceMapper(self._notion_backend)
        self._reducer = reducer or StructuredEntryReducer(config=config, clock=self._clock)
        self._embedding_backend = embedding_backend or build_embedding_backend(config)
        self._lightrag_backend = lightrag_backend or LightRAGHTTPBackend(config=config, embedding_backend=self._embedding_backend)
        self._dispatcher = dispatcher or PipelineDispatcher(config)
        self._committer = committer or PipelineCommitter(config=config, lightrag_backend=self._lightrag_backend, clock=self._clock)
        self._logger = configure_logging(config.settings)

    def full_sync(
        self,
        *,
        datasources: Sequence[str] | None = None,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> SyncBatchResult:
        resolved_datasources = self._resolve_datasources(datasources)
        results: list[SyncEntryResult] = []
        for datasource in resolved_datasources:
            for page in self._notion_backend.query_datasource(datasource):
                results.append(self._process_page(datasource, page, vault_root=vault_root, dry_run=dry_run))
        return self._batch_result('full', resolved_datasources, results)

    def incremental_sync(
        self,
        *,
        datasources: Sequence[str] | None = None,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> SyncBatchResult:
        resolved_datasources = self._resolve_datasources(datasources)
        results: list[SyncEntryResult] = []
        for datasource in resolved_datasources:
            for page in self._notion_backend.query_datasource(datasource):
                try:
                    mapped = self._mapper.map_page(datasource, page)
                except SkipEntryError as exc:
                    results.append(self._skipped_result(datasource, page, str(exc)))
                    continue
                if not self._needs_incremental_sync(mapped, vault_root=vault_root):
                    results.append(
                        SyncEntryResult(
                            datasource=datasource,
                            source_page_id=mapped.source_page_id,
                            status='skipped',
                            relative_path=None,
                            reason='unchanged since last sync',
                            quarantine_path=None,
                            markdown=None,
                        )
                    )
                    continue
                results.append(self._process_mapped_entry(mapped, vault_root=vault_root, dry_run=dry_run))
        return self._batch_result('incremental', resolved_datasources, results)

    def process_single_entry(
        self,
        datasource: str,
        *,
        page: Mapping[str, Any] | None = None,
        page_id: str | None = None,
        vault_root: Path | None = None,
        dry_run: bool = False,
    ) -> SyncEntryResult:
        if page is None:
            if page_id is None:
                raise ValueError('page or page_id is required for single-entry processing')
            page = self._load_page(datasource, page_id)
        return self._process_page(datasource, page, vault_root=vault_root, dry_run=dry_run)

    def commit_reduced_entry(
        self,
        entry: ReducedEntry,
        *,
        vault_root: Path | None = None,
        dry_run: bool = False,
        entrypoint: str = 'persist.process',
        ignore_relative_paths: Sequence[str] = (),
    ) -> CommitResult:
        dispatch = self._dispatcher.dispatch(entry, entrypoint=entrypoint)
        embedding = None if dry_run else self._embedding_backend.embed_documents([entry.markdown])[0]
        return self._committer.commit(
            entry,
            dispatch,
            embedding=embedding,
            vault_root=vault_root,
            dry_run=dry_run,
            ignore_relative_paths=ignore_relative_paths,
        )

    def _process_page(
        self,
        datasource: str,
        page: Mapping[str, Any],
        *,
        vault_root: Path | None,
        dry_run: bool,
    ) -> SyncEntryResult:
        try:
            mapped = self._mapper.map_page(datasource, page)
        except SkipEntryError as exc:
            return self._skipped_result(datasource, page, str(exc))
        return self._process_mapped_entry(mapped, vault_root=vault_root, dry_run=dry_run)

    def _process_mapped_entry(
        self,
        mapped: MappedNotionEntry,
        *,
        vault_root: Path | None,
        dry_run: bool,
    ) -> SyncEntryResult:
        try:
            reduced = self._reducer.reduce(mapped)
            dispatch = self._dispatcher.dispatch(reduced)
            embedding = None if dry_run else self._embedding_backend.embed_documents([reduced.markdown])[0]
            commit_result = self._committer.commit(
                reduced,
                dispatch,
                embedding=embedding,
                vault_root=vault_root,
                dry_run=dry_run,
            )
            return self._to_entry_result(mapped, commit_result)
        except Exception as exc:
            self._logger.exception(
                'persist_process.entry_failed',
                datasource=mapped.datasource,
                source_page_id=mapped.source_page_id,
                title=mapped.title,
            )
            quarantine_result = self._committer.quarantine_mapped_entry(
                mapped,
                reason=str(exc),
                vault_root=vault_root,
                dry_run=dry_run,
            )
            return self._to_entry_result(mapped, quarantine_result)

    def _needs_incremental_sync(self, mapped: MappedNotionEntry, *, vault_root: Path | None) -> bool:
        existing = self._committer.locate_existing(mapped.source, vault_root=vault_root)
        if existing is None:
            return True
        return existing.document.frontmatter.updated < mapped.updated

    def _load_page(self, datasource: str, page_id: str) -> Mapping[str, Any]:
        for page in self._notion_backend.query_datasource(datasource):
            if _require_string(page.get('id'), field='id') == page_id:
                return page
        raise KeyError(f'{datasource}:{page_id}')

    def _resolve_datasources(self, datasources: Sequence[str] | None) -> tuple[str, ...]:
        if datasources is not None:
            return tuple(datasources)
        names: list[str] = []
        seen: set[str] = set()
        for spec in self._notion_backend.datasources.values():
            if spec.name in seen:
                continue
            seen.add(spec.name)
            names.append(spec.name)
        return tuple(names)

    def _skipped_result(self, datasource: str, page: Mapping[str, Any], reason: str) -> SyncEntryResult:
        source_page_id = str(page.get('id', 'unknown'))
        return SyncEntryResult(
            datasource=datasource,
            source_page_id=source_page_id,
            status='skipped',
            relative_path=None,
            reason=reason,
            quarantine_path=None,
            markdown=None,
        )

    def _to_entry_result(self, mapped: MappedNotionEntry, commit_result: CommitResult) -> SyncEntryResult:
        quarantine_path = None
        if commit_result.quarantine is not None:
            quarantine_path = commit_result.quarantine.payload_path
        return SyncEntryResult(
            datasource=mapped.datasource,
            source_page_id=mapped.source_page_id,
            status=commit_result.status,
            relative_path=commit_result.relative_path,
            reason=commit_result.reason,
            quarantine_path=quarantine_path,
            markdown=commit_result.markdown,
        )

    def _batch_result(self, mode: str, datasources: Sequence[str], entries: Sequence[SyncEntryResult]) -> SyncBatchResult:
        counter = Counter(entry.status for entry in entries)
        return SyncBatchResult(
            mode=mode,
            datasources=tuple(datasources),
            entries=tuple(entries),
            counts=dict(counter),
        )
