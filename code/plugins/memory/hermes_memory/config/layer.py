from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Any

from plugins.memory.hermes_memory.core.models import BUILTIN_NOTE_TYPES

from .resources_loader import ResourceLoader, TagRegistry, VaultSpecContract, assert_resource_contracts
from .settings import HermesMemorySettings


@dataclass(frozen=True, slots=True)
class ConfigLayer:
    settings: HermesMemorySettings
    resources: ResourceLoader

    @classmethod
    def from_settings(cls, settings: HermesMemorySettings | None = None) -> 'ConfigLayer':
        resolved_settings = settings or HermesMemorySettings()
        resources = ResourceLoader(resolved_settings)
        assert_resource_contracts(resolved_settings, resources)
        _assert_notion_database_contracts(resolved_settings)
        return cls(settings=resolved_settings, resources=resources)

    @property
    def tag_registry(self) -> TagRegistry:
        return self.resources.tag_registry

    @property
    def vault_spec(self) -> VaultSpecContract:
        return self.resources.vault_spec_contract

    @property
    def allowed_note_types(self) -> tuple[str, ...]:
        merged = list(BUILTIN_NOTE_TYPES)
        for item in self.settings.custom_types:
            normalized = item.strip().lower()
            if normalized and normalized not in merged:
                merged.append(normalized)
        return tuple(merged)

    @property
    def openclaw_config(self) -> Mapping[str, Any]:
        path = self.settings.openclaw_config_path.expanduser()
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        return loaded

    def openclaw_api_key(self, service_name: str) -> str | None:
        skills = self.openclaw_config.get('skills')
        if not isinstance(skills, dict):
            return None
        entries = skills.get('entries')
        if not isinstance(entries, dict):
            return None
        service = entries.get(service_name)
        if not isinstance(service, dict):
            return None
        api_key = service.get('apiKey')
        if isinstance(api_key, str) and api_key.strip():
            return api_key.strip()
        return None

    def resolve_secret(
        self,
        *,
        yaml_value: str | None,
        service_name: str | None = None,
        env_vars: Iterable[str] = (),
    ) -> str | None:
        for env_name in env_vars:
            value = os.getenv(env_name)
            if value and value.strip():
                return value.strip()
        if service_name is not None:
            openclaw_value = self.openclaw_api_key(service_name)
            if openclaw_value is not None:
                return openclaw_value
        if yaml_value and yaml_value.strip():
            return yaml_value.strip()
        return None

    def quarantine_root(self, vault_root: Path | None = None) -> Path:
        base = vault_root or self.settings.vault_root
        if base is None:
            raise ValueError('vault_root is required to construct the quarantine path')
        return base / self.settings.quarantine_dirname

    def attachment_bucket(self, when: date | datetime, vault_root: Path | None = None) -> Path:
        base = vault_root or self.settings.vault_root
        if base is None:
            raise ValueError('vault_root is required to construct the attachment path')
        year = when.strftime('%Y')
        month = when.strftime('%m')
        template = self.vault_spec.attachment_root_template.strip('/').replace('YYYY', year).replace('MM', month)
        return base / template

    def skill_root(self) -> Path:
        return self.settings.skills_root.expanduser()

    def quarantine_bucket(self, when: date | datetime, vault_root: Path | None = None) -> Path:
        if isinstance(when, datetime):
            stamp = when.date().strftime('%Y-%m')
        else:
            stamp = when.strftime('%Y-%m')
        return self.quarantine_root(vault_root=vault_root) / stamp

    def is_quarantined_path(self, path: str | Path, vault_root: Path | None = None) -> bool:
        candidate = Path(path)
        quarantine_root = self.quarantine_root(vault_root=vault_root)
        try:
            candidate.relative_to(quarantine_root)
            return True
        except ValueError:
            pass
        return self.settings.quarantine_dirname in candidate.parts


def _assert_notion_database_contracts(settings: HermesMemorySettings) -> None:
    if not settings.notion.databases:
        return
    allowed_types = set(BUILTIN_NOTE_TYPES)
    allowed_types.update(item.strip().lower() for item in settings.custom_types if item.strip())
    for database in settings.notion.databases:
        if database.type is not None and database.type not in allowed_types:
            raise ValueError(f'notion database type is not registered: {database.type}')
        if database.mapping is None:
            continue
        for source_value, target_type in database.mapping.items():
            if target_type is None:
                continue
            if target_type not in allowed_types:
                raise ValueError(
                    f'notion database mapping target is not registered for {database.name} ({source_value} -> {target_type})'
                )
