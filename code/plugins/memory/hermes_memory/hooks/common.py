from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices


@dataclass(frozen=True, slots=True)
class HookPayload:
    session_id: str | None
    conversation_history: object | None
    model: str | None
    platform: str | None


@dataclass(frozen=True, slots=True)
class AuditState:
    path: Path
    records: tuple[Mapping[str, Any], ...]

    def has_session_hash(self, session_hash: str) -> bool:
        return any(record.get('session_hash') == session_hash for record in self.records)


def parse_hook_payload(
    *,
    session_id: str | None = None,
    conversation_history: object | None = None,
    model: str | None = None,
    platform: str | None = None,
) -> HookPayload:
    return HookPayload(
        session_id=_clean_optional_string(session_id),
        conversation_history=conversation_history,
        model=_clean_optional_string(model),
        platform=_clean_optional_string(platform),
    )


def require_string(value: str | None, *, field: str) -> str:
    if value is None:
        raise ValueError(f'{field} is required')
    return value


def resolve_services(
    *,
    services: HermesMemoryServices | None = None,
    config: ConfigLayer | None = None,
) -> HermesMemoryServices:
    if services is not None:
        return services
    if config is not None:
        return HermesMemoryServices(config=config)
    return HermesMemoryServices()


def require_vault_root(services: HermesMemoryServices, *, vault_root: Path | None = None) -> Path:
    base = vault_root or services.config.settings.vault_root
    if base is None:
        raise ValueError('vault_root is required for hook execution')
    return base


def read_jsonl_records(path: Path) -> tuple[Mapping[str, Any], ...]:
    if not path.exists():
        return ()
    records: list[Mapping[str, Any]] = []
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        loaded = json.loads(line)
        if isinstance(loaded, Mapping):
            records.append(dict(loaded))
    return tuple(records)


def load_audit_state(path: Path) -> AuditState:
    return AuditState(path=path, records=read_jsonl_records(path))


def append_jsonl_record(path: Path, record: Mapping[str, Any], *, dry_run: bool = False) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + '\n')


def write_jsonl_records(path: Path, records: Sequence[Mapping[str, Any]], *, dry_run: bool = False) -> None:
    if dry_run:
        return
    if not records:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = '\n'.join(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) for record in records) + '\n'
    path.write_text(payload, encoding='utf-8')


def collect_non_skill_file_hashes(conversation_history: object | None) -> tuple[str, ...]:
    hashes: set[str] = set()
    for attachment in _iter_attachment_candidates(conversation_history):
        if _is_skill_attachment(attachment):
            continue
        file_identifier = _file_identifier(attachment)
        if file_identifier is None:
            continue
        hashes.add(sha256_hexdigest(file_identifier))
    return tuple(sorted(hashes))


def hash_session_identity(payload: HookPayload) -> str:
    session_id = require_string(payload.session_id, field='session_id')
    model = require_string(payload.model, field='model')
    platform = require_string(payload.platform, field='platform')
    descriptor = json.dumps(
        {
            'session_id': session_id,
            'model': model,
            'platform': platform,
        },
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    )
    return sha256_hexdigest(descriptor)


def _clean_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _iter_attachment_candidates(payload: object | None) -> Iterable[Mapping[str, Any]]:
    stack: list[object] = []
    if payload is not None:
        stack.append(payload)
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            maybe_attachment = _mapping_to_attachment(current)
            if maybe_attachment is not None:
                yield maybe_attachment
            for value in current.values():
                if isinstance(value, Mapping | list | tuple):
                    stack.append(value)
            continue
        if isinstance(current, list | tuple):
            stack.extend(reversed(list(current)))


def _mapping_to_attachment(candidate: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if any(key in candidate for key in ('file_id', 'attachment_id')):
        return candidate
    identifier = candidate.get('id')
    attachment_type = candidate.get('type')
    if isinstance(identifier, str) and isinstance(attachment_type, str) and attachment_type in {'file', 'attachment'}:
        return candidate
    return None


def _is_skill_attachment(candidate: Mapping[str, Any]) -> bool:
    scope = candidate.get('scope')
    if isinstance(scope, str) and scope.strip() == 'skill':
        return True
    destination = candidate.get('destination')
    if isinstance(destination, Mapping):
        scope = destination.get('scope')
        if isinstance(scope, str) and scope.strip() == 'skill':
            return True
    return False


def _file_identifier(candidate: Mapping[str, Any]) -> str | None:
    for key in ('file_id', 'attachment_id', 'id'):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
