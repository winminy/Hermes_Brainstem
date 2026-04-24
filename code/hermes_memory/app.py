from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import os
from pathlib import Path

from hermes_memory.cli import main as doctor_main
from plugins.memory.hermes_memory.core.sync import render_sync_output, run_sync
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices


ServicesFactory = Callable[[], HermesMemoryServices]


def main(argv: Sequence[str] | None = None, *, services_factory: ServicesFactory = HermesMemoryServices) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, 'handler', None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args, services_factory=services_factory))


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog='python -m hermes_memory', description='Hermes Memory Provider CLI entrypoint.')
    subparsers = parser.add_subparsers(dest='command')

    sync_parser = subparsers.add_parser('sync', help='Sync configured Notion databases into the vault.')
    sync_parser.add_argument('--config', help='Path to config.yaml. Defaults to $HERMES_MEMORY_CONFIG_FILE or ./config.yaml.')
    sync_parser.add_argument('--since', help='Sync only pages created or edited on/after YYYY-MM-DD.')
    sync_parser.add_argument('--db-name', help='Only sync the named Notion database from notion.databases.')
    sync_parser.add_argument('--dry-run', action='store_true', help='Show targets without writing vault files.')
    sync_parser.set_defaults(handler=_handle_sync)

    doctor_parser = subparsers.add_parser('doctor', help='Run deployment validation checks.')
    doctor_parser.add_argument('--config', help='Path to config.yaml. Defaults to $HERMES_MEMORY_CONFIG_FILE or ./config.yaml.')
    doctor_parser.add_argument('--timeout', type=float, default=2.0, help='HTTP timeout in seconds for local LightRAG health checks.')
    doctor_parser.set_defaults(handler=_handle_doctor)
    return parser


def _handle_sync(args: Namespace, *, services_factory: ServicesFactory) -> int:
    if args.since is not None:
        _validate_since(args.since)
    with _config_override(args.config):
        result = run_sync(
            services_factory(),
            db_names=(args.db_name,) if isinstance(args.db_name, str) and args.db_name.strip() else None,
            since=args.since,
            dry_run=bool(args.dry_run),
        )
    print(render_sync_output(result))
    return 0


def _handle_doctor(args: Namespace, *, services_factory: ServicesFactory) -> int:
    del services_factory
    doctor_args: list[str] = []
    if args.config:
        doctor_args.extend(['--config', args.config])
    doctor_args.extend(['--timeout', str(args.timeout)])
    return doctor_main(doctor_args)


def _validate_since(raw: str) -> None:
    from datetime import datetime

    try:
        datetime.strptime(raw, '%Y-%m-%d')
    except ValueError as exc:  # pragma: no cover - argparse handles presentation
        raise SystemExit(f'error: --since must be YYYY-MM-DD: {raw}') from exc


@contextmanager
def _config_override(config_path: str | None) -> Iterator[None]:
    if config_path is None:
        yield
        return
    env_name = 'HERMES_MEMORY_CONFIG_FILE'
    previous = os.environ.get(env_name)
    os.environ[env_name] = str(Path(config_path).expanduser())
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = previous


__all__ = ['build_parser', 'main']
