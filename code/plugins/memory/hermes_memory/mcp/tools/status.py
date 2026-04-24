from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plugins.memory.hermes_memory.mcp.schema_loader import load_schema
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices

from .base import ManagedTool


def build_status_tool(services: HermesMemoryServices, *, tool_names: tuple[str, ...]) -> ManagedTool:
    def handler(arguments: Mapping[str, Any]) -> dict[str, Any]:
        del arguments
        vault_root = services.config.settings.vault_root
        note_roots: dict[str, bool] = {}
        if vault_root is not None:
            for note_root in services.config.vault_spec.provider_managed_note_roots:
                note_roots[note_root.rstrip('/')] = (vault_root / note_root.rstrip('/')).exists()
        healthy = vault_root is not None
        return {
            'healthy': healthy,
            'server_name': services.config.settings.mcp.server_name,
            'server_version': services.config.settings.mcp.server_version,
            'configured_tools': list(tool_names),
            'vault_root': None if vault_root is None else str(vault_root),
            'skills_root': str(services.config.skill_root()),
            'checks': {
                'vault_root_configured': vault_root is not None,
                'provider_managed_note_roots_present': note_roots,
                'quarantine_dirname': services.config.settings.quarantine_dirname,
                'lightrag_base_url': services.config.settings.lightrag.base_url,
            },
        }

    return ManagedTool(
        name='status',
        title='Hermes Status',
        description='Provider health and configuration status.',
        input_schema=load_schema('status.input.json'),
        output_schema=load_schema('status.output.json'),
        handler=handler,
    )
