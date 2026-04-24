from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest
from plugins.memory.hermes_memory.hooks.common import append_jsonl_record, parse_hook_payload, require_vault_root, resolve_services
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.search import read as read_note


_AUDIT_FILENAME = '.hermes-quarantine-sweep-audit.jsonl'


@dataclass(frozen=True, slots=True)
class QuarantineSweepEntryResult:
    relative_path: str
    status: str
    quarantine_path: str | None
    reason: str | None
    payload_hash: str | None


@dataclass(frozen=True, slots=True)
class QuarantineSweepResult:
    audit_path: str
    entries: tuple[QuarantineSweepEntryResult, ...]


def run_quarantine_sweep(
    *,
    session_id: str | None = None,
    conversation_history: object | None = None,
    model: str | None = None,
    platform: str | None = None,
    services: HermesMemoryServices | None = None,
    config: ConfigLayer | None = None,
    vault_root: Path | None = None,
    dry_run: bool = False,
) -> QuarantineSweepResult:
    parse_hook_payload(
        session_id=session_id,
        conversation_history=conversation_history,
        model=model,
        platform=platform,
    )
    resolved_services = resolve_services(services=services, config=config)
    resolved_vault_root = require_vault_root(resolved_services, vault_root=vault_root)
    audit_path = resolved_vault_root / 'inbox' / _AUDIT_FILENAME
    results: list[QuarantineSweepEntryResult] = []
    for path in _candidate_note_paths(resolved_services, vault_root=resolved_vault_root):
        result = _inspect_note(
            path,
            services=resolved_services,
            vault_root=resolved_vault_root,
            dry_run=dry_run,
        )
        results.append(result)
        if result.payload_hash is None:
            continue
        append_jsonl_record(
            audit_path,
            {
                'relative_path': result.relative_path,
                'payload_hash': result.payload_hash,
                'quarantine_path': result.quarantine_path,
                'reason': result.reason,
                'status': result.status,
            },
            dry_run=dry_run,
        )
    return QuarantineSweepResult(audit_path=str(audit_path), entries=tuple(results))


def _candidate_note_paths(services: HermesMemoryServices, *, vault_root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for root_name in services.config.vault_spec.provider_managed_note_roots:
        root = vault_root / root_name.rstrip('/')
        if not root.exists():
            continue
        for path in sorted(root.rglob('*.md')):
            paths.append(path)
    return tuple(paths)


def _inspect_note(
    path: Path,
    *,
    services: HermesMemoryServices,
    vault_root: Path,
    dry_run: bool,
) -> QuarantineSweepEntryResult:
    relative_path = path.relative_to(vault_root).as_posix()
    try:
        entry = read_note(relative_path, config=services.config, vault_root=vault_root)
    except Exception as exc:
        quarantine_path, payload_hash = _move_to_quarantine(path, reason=str(exc), services=services, vault_root=vault_root, dry_run=dry_run)
        return QuarantineSweepEntryResult(
            relative_path=relative_path,
            status='quarantined',
            quarantine_path=quarantine_path,
            reason=str(exc),
            payload_hash=payload_hash,
        )

    expected_area = relative_path.split('/', 1)[0]
    actual_area = entry.frontmatter.area.value
    if actual_area != expected_area:
        reason = f'frontmatter area/path mismatch: {actual_area} != {expected_area}'
        quarantine_path, payload_hash = _move_to_quarantine(path, reason=reason, services=services, vault_root=vault_root, dry_run=dry_run)
        return QuarantineSweepEntryResult(
            relative_path=relative_path,
            status='quarantined',
            quarantine_path=quarantine_path,
            reason=reason,
            payload_hash=payload_hash,
        )

    return QuarantineSweepEntryResult(
        relative_path=relative_path,
        status='clean',
        quarantine_path=None,
        reason=None,
        payload_hash=None,
    )


def _move_to_quarantine(
    path: Path,
    *,
    reason: str,
    services: HermesMemoryServices,
    vault_root: Path,
    dry_run: bool,
) -> tuple[str, str]:
    payload_bytes = path.read_bytes()
    payload_hash = sha256_hexdigest(payload_bytes)
    bucket = services.config.quarantine_bucket(
        datetime.now(ZoneInfo(services.config.settings.timezone)),
        vault_root=vault_root,
    )
    target = _next_available_path(bucket, path.stem)
    reason_path = target.with_suffix(target.suffix + '.reason.txt')
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
        reason_path.write_text(reason + '\n', encoding='utf-8')
        _mark_read_only(target)
        _mark_read_only(reason_path)
    return str(target), payload_hash


def _next_available_path(root: Path, stem: str) -> Path:
    candidate = root / f'{stem}.md'
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        alternative = root / f'{stem}-{counter}.md'
        if not alternative.exists():
            return alternative
        counter += 1


def _mark_read_only(path: Path) -> None:
    try:
        os.chmod(path, 0o444)
    except OSError:
        return


__all__ = [
    'QuarantineSweepEntryResult',
    'QuarantineSweepResult',
    'run_quarantine_sweep',
]
