from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
from typing import Any, Protocol

from plugins.memory.hermes_memory.config.layer import ConfigLayer

from . import run_with_retry


class GDriveMCPBackend(Protocol):
    def attach(self, file_path: Path, *, metadata: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class GDriveAttachRequest:
    file_path: Path
    metadata: Mapping[str, Any]


class SubprocessGDriveMCPBackend:
    def __init__(self, *, config: ConfigLayer, command: Sequence[str] | None = None) -> None:
        self._config = config
        self._command = list(command) if command is not None else ['hermes', 'mcp', 'call', config.settings.gdrive_mcp.server_name, 'persist.attach']

    def attach(self, file_path: Path, *, metadata: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if not self._config.settings.gdrive_mcp.enabled:
            raise RuntimeError('gdrive_mcp backend is disabled. Enable it before persist.attach calls.')
        request = GDriveAttachRequest(file_path=file_path, metadata=dict(metadata or {}))
        return run_with_retry(lambda: self._run(request))

    def _run(self, request: GDriveAttachRequest) -> Mapping[str, Any]:
        payload = {'file_path': str(request.file_path), 'metadata': dict(request.metadata)}
        completed = subprocess.run(
            self._command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=self._config.settings.gdrive_mcp.timeout_seconds,
        )
        data = json.loads(completed.stdout or '{}')
        if not isinstance(data, dict):
            raise ValueError('gdrive mcp response must be a JSON object')
        return data
