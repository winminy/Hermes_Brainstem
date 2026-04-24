from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
import importlib.util
import os
from pathlib import Path
from typing import Literal

import httpx
import yaml

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings

CheckStatus = Literal['pass', 'warn', 'fail']
_RESOURCE_PACKAGE = 'plugins.memory.hermes_memory.config.resources'
_REQUIRED_META_DOCS = (
    'TAGS.md',
    'data_ops/binary_policy.md',
    'data_ops/file_policy.md',
    'data_ops/retention.md',
    'notion_datasource_map.md',
    'self_reference/hook_registry.md',
    'self_reference/persist_policy.md',
    'self_reference/quarantine_policy.md',
    'self_reference/scope_policy.md',
    'skills/default/notion_sync.md',
    'skills/default/persist_attach.md',
    'skills/default/quarantine_sweep.md',
    'skills/default/session_close.md',
    'skills/skill_registry.md',
    'skills/skill_spec.md',
    'vault_spec.md',
)


@dataclass(frozen=True, slots=True)
class DoctorCheckResult:
    name: str
    status: CheckStatus
    reason: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    config_path: Path
    checks: tuple[DoctorCheckResult, ...]

    @property
    def pass_count(self) -> int:
        return sum(1 for check in self.checks if check.status == 'pass')

    @property
    def warn_count(self) -> int:
        return sum(1 for check in self.checks if check.status == 'warn')

    @property
    def fail_count(self) -> int:
        return sum(1 for check in self.checks if check.status == 'fail')

    @property
    def exit_code(self) -> int:
        return 0 if self.fail_count == 0 else 1


@dataclass(frozen=True, slots=True)
class ResolvedSecret:
    value: str | None
    source: str | None


def doctor() -> None:
    raise SystemExit(main())


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_doctor(config_path=Path(args.config) if args.config is not None else None, timeout_seconds=args.timeout)
    print(render_report(report))
    return report.exit_code


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog='hermes-memory-doctor', description='Validate Hermes Memory Provider deployment prerequisites.')
    parser.add_argument('--config', help='Path to config.yaml. Defaults to $HERMES_MEMORY_CONFIG_FILE or ./config.yaml.')
    parser.add_argument('--timeout', type=float, default=2.0, help='HTTP timeout in seconds for local LightRAG health checks.')
    return parser


def run_doctor(*, config_path: Path | None = None, timeout_seconds: float = 2.0) -> DoctorReport:
    resolved_config_path = _resolve_config_path(config_path)
    checks: list[DoctorCheckResult] = []

    config_check, config = _check_config(resolved_config_path)
    checks.append(config_check)
    checks.append(_check_vault_root(config))
    checks.append(_check_lightrag(config, timeout_seconds=timeout_seconds))
    checks.append(_check_embedding_backend(config))
    checks.append(_check_notion_api_key(config))
    checks.append(_check_packaged_meta_docs())
    return DoctorReport(config_path=resolved_config_path, checks=tuple(checks))


def render_report(report: DoctorReport) -> str:
    lines = [f'Hermes Memory Doctor — config={report.config_path}']
    for check in report.checks:
        lines.append(f'[{check.status.upper()}] {check.name}: {check.reason}')
    lines.append(f'Summary: {report.pass_count} pass, {report.warn_count} warn, {report.fail_count} fail')
    lines.append(f'Exit code: {report.exit_code}')
    return '\n'.join(lines)


def _resolve_config_path(config_path: Path | None) -> Path:
    raw_path = config_path or Path(os.getenv('HERMES_MEMORY_CONFIG_FILE', 'config.yaml'))
    return raw_path.expanduser().resolve()


def _check_config(config_path: Path) -> tuple[DoctorCheckResult, ConfigLayer | None]:
    if not config_path.exists():
        return DoctorCheckResult('config.yaml parsing', 'fail', f'config file not found: {config_path}'), None
    if not config_path.is_file():
        return DoctorCheckResult('config.yaml parsing', 'fail', f'config path is not a file: {config_path}'), None
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        return DoctorCheckResult('config.yaml parsing', 'fail', f'config YAML could not be parsed: {exc}'), None
    if not isinstance(loaded, dict):
        return DoctorCheckResult('config.yaml parsing', 'fail', 'config YAML must deserialize to a mapping object'), None
    try:
        with _config_file_override(config_path):
            config = ConfigLayer.from_settings(HermesMemorySettings())
    except Exception as exc:
        return DoctorCheckResult('config.yaml parsing', 'fail', f'settings bootstrap failed: {exc}'), None
    return DoctorCheckResult('config.yaml parsing', 'pass', f'parsed successfully from {config_path}'), config


def _check_vault_root(config: ConfigLayer | None) -> DoctorCheckResult:
    if config is None:
        return DoctorCheckResult('vault root access', 'fail', 'blocked because config.yaml parsing failed')
    vault_root = config.settings.vault_root
    if vault_root is None:
        return DoctorCheckResult('vault root access', 'fail', 'vault_root is not configured')
    resolved_vault_root = vault_root.expanduser()
    if not resolved_vault_root.exists() or not resolved_vault_root.is_dir():
        return DoctorCheckResult('vault root access', 'fail', f'vault root is missing or not a directory: {resolved_vault_root}')
    if not os.access(resolved_vault_root, os.R_OK | os.W_OK | os.X_OK):
        return DoctorCheckResult('vault root access', 'fail', f'vault root is not readable/writable/executable: {resolved_vault_root}')
    return DoctorCheckResult('vault root access', 'pass', f'vault root is accessible: {resolved_vault_root}')


def _check_lightrag(config: ConfigLayer | None, *, timeout_seconds: float) -> DoctorCheckResult:
    if config is None:
        return DoctorCheckResult('LightRAG response', 'fail', 'blocked because config.yaml parsing failed')
    base_url = config.settings.lightrag.base_url.rstrip('/')
    url = f'{base_url}/openapi.json'
    try:
        payload = _http_get_json(url, timeout_seconds=timeout_seconds)
    except (httpx.HTTPError, ValueError) as exc:
        return DoctorCheckResult('LightRAG response', 'fail', f'GET {url} failed: {exc}')
    if not isinstance(payload, dict):
        return DoctorCheckResult('LightRAG response', 'fail', f'GET {url} did not return a JSON object')
    return DoctorCheckResult('LightRAG response', 'pass', f'GET {url} returned JSON successfully')


def _check_embedding_backend(config: ConfigLayer | None) -> DoctorCheckResult:
    if config is None:
        return DoctorCheckResult('embedding backend load', 'fail', 'blocked because config.yaml parsing failed')
    backend_name = config.settings.embedding.backend
    if backend_name == 'api':
        secret = _resolve_secret_with_source(
            config,
            yaml_value=config.settings.embedding.api.api_key,
            service_name=config.settings.embedding.api.service_name,
            env_vars=config.settings.embedding.api.env_vars,
        )
        if secret.value is None:
            return DoctorCheckResult('embedding backend load', 'fail', 'embedding.backend=api requires an API key via env, openclaw.json, or yaml')
        if _looks_like_placeholder(secret.value):
            return DoctorCheckResult('embedding backend load', 'fail', f'embedding API key from {secret.source} still looks like a placeholder')
        if not _module_available('openai'):
            return DoctorCheckResult('embedding backend load', 'fail', 'embedding.backend=api selected but openai extra is not installed')
        provider = config.settings.embedding.api.provider
        model = config.settings.embedding.api.model
        return DoctorCheckResult('embedding backend load', 'pass', f'backend=api ready via {provider}/{model} (secret source: {secret.source})')
    if backend_name == 'local':
        if not _module_available('sentence_transformers'):
            return DoctorCheckResult('embedding backend load', 'fail', 'embedding.backend=local selected but sentence-transformers extra is not installed')
        model_name = config.settings.embedding.local.model_name
        return DoctorCheckResult('embedding backend load', 'pass', f'backend=local import available for model {model_name}')
    return DoctorCheckResult('embedding backend load', 'fail', f'unsupported embedding backend configured: {backend_name}')


def _check_notion_api_key(config: ConfigLayer | None) -> DoctorCheckResult:
    if config is None:
        return DoctorCheckResult('Notion API key', 'fail', 'blocked because config.yaml parsing failed')
    secret = _resolve_secret_with_source(
        config,
        yaml_value=config.settings.notion.api_key,
        service_name=config.settings.notion.service_name,
        env_vars=config.settings.notion.env_vars,
    )
    if secret.value is None:
        return DoctorCheckResult('Notion API key', 'fail', 'Notion API key is missing from env, openclaw.json, and yaml')
    if _looks_like_placeholder(secret.value):
        return DoctorCheckResult('Notion API key', 'fail', f'Notion API key from {secret.source} still looks like a placeholder')
    if not _module_available('notion_client'):
        return DoctorCheckResult('Notion API key', 'fail', 'notion-client dependency is not installed')
    return DoctorCheckResult('Notion API key', 'pass', f'Notion API key resolved successfully from {secret.source}')


def _check_packaged_meta_docs() -> DoctorCheckResult:
    discovered = _packaged_meta_docs()
    missing = [path for path in _REQUIRED_META_DOCS if path not in discovered]
    extras = [path for path in discovered if path not in _REQUIRED_META_DOCS]
    if missing:
        return DoctorCheckResult('packaged meta docs', 'fail', f'missing {len(missing)} required docs: {", ".join(missing)}')
    if extras:
        return DoctorCheckResult('packaged meta docs', 'warn', f'found required 16 docs plus {len(extras)} extra markdown files')
    return DoctorCheckResult('packaged meta docs', 'pass', 'all 16 packaged meta docs are present')


def _packaged_meta_docs() -> tuple[str, ...]:
    root = files(_RESOURCE_PACKAGE).joinpath('_system')
    return tuple(sorted(_iter_markdown_paths(root)))


def _iter_markdown_paths(root: Traversable, prefix: str = '') -> Iterator[str]:
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        relative_name = f'{prefix}{child.name}'
        if child.is_dir():
            yield from _iter_markdown_paths(child, prefix=f'{relative_name}/')
        elif child.is_file() and child.name.endswith('.md'):
            yield relative_name


def _resolve_secret_with_source(
    config: ConfigLayer,
    *,
    yaml_value: str | None,
    service_name: str | None,
    env_vars: Sequence[str],
) -> ResolvedSecret:
    for env_name in env_vars:
        value = os.getenv(env_name)
        if value is not None and value.strip():
            return ResolvedSecret(value=value.strip(), source=f'env:{env_name}')
    if service_name is not None:
        openclaw_value = config.openclaw_api_key(service_name)
        if openclaw_value is not None:
            return ResolvedSecret(value=openclaw_value, source=f'openclaw:{service_name}')
    if yaml_value is not None and yaml_value.strip():
        return ResolvedSecret(value=yaml_value.strip(), source='yaml')
    return ResolvedSecret(value=None, source=None)


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized.startswith('${') and normalized.endswith('}'):
        return True
    placeholder_markers = ('changeme', 'placeholder', 'replace', 'your_', 'your-', '<your', 'example')
    return any(marker in normalized for marker in placeholder_markers)


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _http_get_json(url: str, *, timeout_seconds: float) -> object:
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


@contextmanager
def _config_file_override(config_path: Path) -> Iterator[None]:
    env_name = 'HERMES_MEMORY_CONFIG_FILE'
    had_previous = env_name in os.environ
    previous = os.environ.get(env_name)
    os.environ[env_name] = str(config_path)
    try:
        yield
    finally:
        if had_previous and previous is not None:
            os.environ[env_name] = previous
        else:
            os.environ.pop(env_name, None)


__all__ = [
    'DoctorCheckResult',
    'DoctorReport',
    'build_parser',
    'doctor',
    'main',
    'render_report',
    'run_doctor',
]
