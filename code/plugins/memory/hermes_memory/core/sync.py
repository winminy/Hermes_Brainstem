from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import json
from pathlib import Path
from typing import TYPE_CHECKING

from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.pipeline.persist_process import SyncEntryResult

if TYPE_CHECKING:
    from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices


DEFAULT_LAST_SYNC_PATH = Path('data/last_sync.json')


@dataclass(frozen=True, slots=True)
class SyncDatabaseResult:
    name: str
    count: int
    entries: tuple[SyncEntryResult, ...]
    since: str | None = None


@dataclass(frozen=True, slots=True)
class SyncRunResult:
    databases: tuple[SyncDatabaseResult, ...]
    dry_run: bool

    @property
    def total_count(self) -> int:
        return sum(database.count for database in self.databases)

    @property
    def summary(self) -> str:
        parts = [f'{database.name} {database.count}건' for database in self.databases]
        detail = ', '.join(parts) if parts else '대상 DB 없음'
        prefix = '동기화 예정' if self.dry_run else '동기화 완료'
        return f'{prefix}: {detail} (총 {self.total_count}건)'


@dataclass(frozen=True, slots=True)
class LastSyncState:
    last_sync: str | None
    per_db: dict[str, str]


class LastSyncStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or DEFAULT_LAST_SYNC_PATH).expanduser()

    def load(self) -> LastSyncState:
        if not self.path.exists():
            return LastSyncState(last_sync=None, per_db={})
        raw = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            return LastSyncState(last_sync=None, per_db={})
        raw_per_db = raw.get('per_db')
        per_db = {str(key): str(value) for key, value in raw_per_db.items()} if isinstance(raw_per_db, dict) else {}
        raw_last_sync = raw.get('last_sync')
        last_sync = str(raw_last_sync) if isinstance(raw_last_sync, str) and raw_last_sync.strip() else None
        return LastSyncState(last_sync=last_sync, per_db=per_db)

    def save(self, state: LastSyncState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'last_sync': state.last_sync,
            'per_db': state.per_db,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def resolve_sync_datasources(services: HermesMemoryServices, db_names: tuple[str, ...] | None = None) -> tuple[str, ...]:
    if db_names is not None:
        return db_names
    names: list[str] = []
    seen: set[str] = set()
    for spec in services.notion_backend.datasources.values():
        if spec.name in seen:
            continue
        seen.add(spec.name)
        names.append(spec.name)
    return tuple(names)


def run_sync(
    services: HermesMemoryServices,
    *,
    db_names: tuple[str, ...] | None = None,
    since: str | None = None,
    dry_run: bool = False,
    vault_root: Path | None = None,
) -> SyncRunResult:
    resolved_vault_root = vault_root or services.config.settings.vault_root
    if resolved_vault_root is None:
        raise ValueError('vault_root is not configured')
    databases: list[SyncDatabaseResult] = []
    for database_name in resolve_sync_datasources(services, db_names):
        pages = services.notion_backend.query_datasource(database_name, since=since)
        entries = tuple(
            services.pipeline.process_single_entry(
                database_name,
                page=page,
                vault_root=resolved_vault_root,
                dry_run=dry_run,
            )
            for page in pages
        )
        databases.append(SyncDatabaseResult(name=database_name, count=len(pages), entries=entries, since=since))
    return SyncRunResult(databases=tuple(databases), dry_run=dry_run)


def run_incremental_sync(
    services: HermesMemoryServices,
    *,
    clock: Clock | None = None,
    last_sync_path: Path | None = None,
    db_names: tuple[str, ...] | None = None,
    vault_root: Path | None = None,
    dry_run: bool = False,
) -> SyncRunResult:
    store = LastSyncStore(last_sync_path)
    state = store.load()
    timestamp = _utc_timestamp(clock or SystemClock('UTC'))
    results: list[SyncDatabaseResult] = []
    per_db = dict(state.per_db)
    for database_name in resolve_sync_datasources(services, db_names):
        since = per_db.get(database_name) or state.last_sync
        result = run_sync(
            services,
            db_names=(database_name,),
            since=since,
            dry_run=dry_run,
            vault_root=vault_root,
        )
        results.extend(result.databases)
        if not dry_run:
            per_db[database_name] = timestamp
    if not dry_run:
        store.save(LastSyncState(last_sync=timestamp, per_db=per_db))
    return SyncRunResult(databases=tuple(results), dry_run=dry_run)


def render_sync_output(result: SyncRunResult) -> str:
    lines = [result.summary]
    for database in result.databases:
        lines.append(f'- {database.name}: {database.count}건')
        if result.dry_run:
            for entry in database.entries:
                target = entry.relative_path or '(target pending)'
                lines.append(f'  - {entry.source_page_id}: {entry.status} -> {target}')
    return '\n'.join(lines)


def _utc_timestamp(clock: Clock) -> str:
    current = clock.now()
    aware = current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


__all__ = [
    'DEFAULT_LAST_SYNC_PATH',
    'LastSyncState',
    'LastSyncStore',
    'SyncDatabaseResult',
    'SyncRunResult',
    'render_sync_output',
    'resolve_sync_datasources',
    'run_incremental_sync',
    'run_sync',
]
