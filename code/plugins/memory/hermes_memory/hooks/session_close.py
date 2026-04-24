from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.hooks.common import (
    append_jsonl_record,
    collect_non_skill_file_hashes,
    hash_session_identity,
    load_audit_state,
    parse_hook_payload,
    read_jsonl_records,
    require_vault_root,
    resolve_services,
    write_jsonl_records,
)
from plugins.memory.hermes_memory.inbox import InboxProcessResult
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.pipeline import SyncBatchResult
from plugins.memory.hermes_memory.search import SearchFilters, direct_search


_AUDIT_FILENAME = '.hermes-session-close-audit.jsonl'
_QUEUE_NOTIFICATION_TAG = 'needs-confirmation'


@dataclass(frozen=True, slots=True)
class SessionCloseEntryResult:
    relative_path: str
    status: str
    knowledge_path: str | None
    quarantine_path: str | None
    reason: str | None
    reason_tag: str | None
    merge_queue_action: str


@dataclass(frozen=True, slots=True)
class SessionCloseResult:
    session_id: str
    session_hash: str
    duplicate_audit: bool
    audit_path: str
    queue_path: str
    sync_result: SyncBatchResult
    entries: tuple[SessionCloseEntryResult, ...]
    audited_file_hashes: tuple[str, ...]


def run_session_close(
    *,
    session_id: str | None = None,
    conversation_history: object | None = None,
    model: str | None = None,
    platform: str | None = None,
    services: HermesMemoryServices | None = None,
    config: ConfigLayer | None = None,
    vault_root: Path | None = None,
    dry_run: bool = False,
) -> SessionCloseResult:
    payload = parse_hook_payload(
        session_id=session_id,
        conversation_history=conversation_history,
        model=model,
        platform=platform,
    )
    resolved_services = resolve_services(services=services, config=config)
    resolved_vault_root = require_vault_root(resolved_services, vault_root=vault_root)
    resolved_session_id = payload.session_id
    if resolved_session_id is None:
        raise ValueError('session_close requires session_id')
    session_hash = hash_session_identity(payload)
    audit_path = resolved_vault_root / 'inbox' / _AUDIT_FILENAME
    audit_state = load_audit_state(audit_path)
    duplicate_audit = audit_state.has_session_hash(session_hash)
    audited_file_hashes = collect_non_skill_file_hashes(payload.conversation_history)

    sync_result = resolved_services.pipeline.incremental_sync(
        datasources=_resolve_daily_datasources(resolved_services),
        vault_root=resolved_vault_root,
        dry_run=dry_run,
    )

    queue_path = resolved_vault_root / 'inbox' / resolved_services.config.settings.inbox.merge_queue_filename
    merge_queue_records = read_jsonl_records(queue_path)
    merge_queue_by_path: dict[str, dict[str, Any]] = {}
    for record in merge_queue_records:
        normalized_path = _normalize_entry_path(record.get('entry_path'))
        if normalized_path is None:
            continue
        merge_queue_by_path[normalized_path] = dict(record)

    entry_results: list[SessionCloseEntryResult] = []
    unresolved_queue_records: list[Mapping[str, Any]] = []
    remaining_queue_paths = set(merge_queue_by_path)
    for relative_path in _inbox_note_paths(resolved_services, vault_root=resolved_vault_root):
        absolute_path = (resolved_vault_root / relative_path).resolve()
        queue_record = merge_queue_by_path.get(str(absolute_path))
        review = resolved_services.inbox_runner.review_existing_entry(
            absolute_path,
            vault_root=resolved_vault_root,
            dry_run=dry_run,
            notification_reason_tag=_QUEUE_NOTIFICATION_TAG if queue_record is not None else None,
        )
        merge_queue_action = _queue_action(review, has_queue_record=queue_record is not None)
        if queue_record is not None:
            remaining_queue_paths.discard(str(absolute_path))
            if merge_queue_action == 'retained':
                unresolved_queue_records.append(
                    _updated_queue_record(
                        queue_record,
                        review=review,
                    )
                )
        entry_results.append(
            SessionCloseEntryResult(
                relative_path=relative_path,
                status=review.status,
                knowledge_path=review.knowledge_path,
                quarantine_path=review.quarantine_path,
                reason=review.reason,
                reason_tag=review.reason_tag,
                merge_queue_action=merge_queue_action,
            )
        )

    for unresolved_path in sorted(remaining_queue_paths):
        unresolved_record = merge_queue_by_path[unresolved_path]
        if Path(unresolved_path).exists():
            unresolved_queue_records.append(_updated_queue_record(unresolved_record, review=None))

    write_jsonl_records(queue_path, unresolved_queue_records, dry_run=dry_run)
    if not duplicate_audit:
        append_jsonl_record(
            audit_path,
            {
                'session_hash': session_hash,
                'session_id': resolved_session_id,
                'model': payload.model,
                'platform': payload.platform,
                'audited_file_hashes': list(audited_file_hashes),
                'sync_counts': dict(sync_result.counts),
                'reviewed_paths': [entry.relative_path for entry in entry_results],
                'queue_path': str(queue_path),
            },
            dry_run=dry_run,
        )

    return SessionCloseResult(
        session_id=resolved_session_id,
        session_hash=session_hash,
        duplicate_audit=duplicate_audit,
        audit_path=str(audit_path),
        queue_path=str(queue_path),
        sync_result=sync_result,
        entries=tuple(entry_results),
        audited_file_hashes=audited_file_hashes,
    )


def _resolve_daily_datasources(services: HermesMemoryServices) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for spec in services.notion_backend.datasources.values():
        if spec.name in seen:
            continue
        if spec.scan_mode != 'daily_auto':
            continue
        seen.add(spec.name)
        names.append(spec.name)
    return tuple(names)


def _inbox_note_paths(services: HermesMemoryServices, *, vault_root: Path) -> tuple[str, ...]:
    hits = direct_search(
        '',
        config=services.config,
        filters=SearchFilters(area='inbox'),
        vault_root=vault_root,
        top_k=10_000,
    )
    return tuple(hit.metadata.relative_path for hit in hits if hit.metadata.relative_path.endswith('.md'))


def _normalize_entry_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return str(Path(value).resolve())


def _queue_action(review: InboxProcessResult, *, has_queue_record: bool) -> str:
    if not has_queue_record:
        return 'not-queued'
    if review.knowledge_path is not None:
        return 'consumed-promoted'
    if review.quarantine_path is not None:
        return 'consumed-quarantined'
    return 'retained'


def _updated_queue_record(
    record: Mapping[str, Any],
    *,
    review: InboxProcessResult | None,
) -> Mapping[str, Any]:
    payload = dict(record)
    payload['notification_tag'] = _QUEUE_NOTIFICATION_TAG
    if review is not None:
        payload['reason'] = review.reason
        payload['reason_tag'] = review.reason_tag or _QUEUE_NOTIFICATION_TAG
        payload['status'] = review.status
    else:
        payload.setdefault('status', 'pending')
    return payload


__all__ = [
    'SessionCloseEntryResult',
    'SessionCloseResult',
    'run_session_close',
]
