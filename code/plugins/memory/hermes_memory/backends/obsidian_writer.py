from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from filelock import FileLock

from plugins.memory.hermes_memory.config.layer import ConfigLayer


class ObsidianWriterError(RuntimeError):
    """Raised when an Obsidian write target cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ObsidianWriteResult:
    mode: Literal['fs', 'advanced-uri']
    target: str


class ObsidianWriter:
    def __init__(self, *, config: ConfigLayer) -> None:
        self._config = config

    def write_markdown(self, relative_path: str | Path, content: str, *, vault_root: Path | None = None) -> ObsidianWriteResult:
        mode = self._config.settings.obsidian_writer.mode
        if mode == 'advanced-uri':
            return ObsidianWriteResult(mode='advanced-uri', target=self.build_advanced_uri(relative_path))
        target_path = self._resolve_target_path(relative_path, vault_root=vault_root)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(f'{target_path}.lock', timeout=self._config.settings.obsidian_writer.filelock_timeout_seconds)
        with lock:
            target_path.write_text(content, encoding='utf-8')
        return ObsidianWriteResult(mode='fs', target=str(target_path))

    def build_advanced_uri(self, relative_path: str | Path) -> str:
        vault_name = self._config.settings.obsidian_writer.vault_name
        if vault_name is None:
            raise ObsidianWriterError('obsidian_writer.vault_name is required for advanced-uri mode')
        path_value = str(relative_path).replace('\\', '/')
        base = self._config.settings.obsidian_writer.advanced_uri_base
        return f'{base}?vault={quote(vault_name)}&filepath={quote(path_value)}'

    def _resolve_target_path(self, relative_path: str | Path, *, vault_root: Path | None = None) -> Path:
        base = vault_root or self._config.settings.vault_root
        if base is None:
            raise ObsidianWriterError('vault_root is required for filesystem writer mode')
        return base / Path(relative_path)
