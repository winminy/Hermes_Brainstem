from __future__ import annotations

from pathlib import Path

import pytest

from hermes_memory.cli import main, run_doctor
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings


def test_config_example_loads_and_exposes_all_packaged_meta_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('HERMES_MEMORY_CONFIG_FILE', str(root / 'config.example.yaml'))

    settings = HermesMemorySettings()
    config = ConfigLayer.from_settings(settings)

    assert settings.mcp.server_version == '0.14.0'
    assert len(config.resources.system_markdown_paths()) == 16
    assert 'skills/default/session_close.md' in config.resources.system_markdown_paths()


def test_doctor_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(['--help'])

    assert excinfo.value.code == 0
    assert 'hermes-memory-doctor' in capsys.readouterr().out


def test_run_doctor_reports_all_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault_root = tmp_path / 'vault'
    vault_root.mkdir()
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '\n'.join(
            [
                f'vault_root: {vault_root}',
                'notion:',
                '  api_key: secret_test_notion_key',
                'embedding:',
                '  backend: api',
                '  api:',
                '    api_key: sk-test-embedding-key',
                'mcp:',
                '  server_version: 0.14.0',
            ]
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr('hermes_memory.cli._http_get_json', lambda url, timeout_seconds: {'openapi': '3.1.0', 'url': url, 'timeout': timeout_seconds})
    monkeypatch.setattr('hermes_memory.cli._module_available', lambda module_name: True)

    report = run_doctor(config_path=config_path, timeout_seconds=1.5)

    assert [check.status for check in report.checks] == ['pass', 'pass', 'pass', 'pass', 'pass', 'pass']
    assert report.exit_code == 0
    assert report.fail_count == 0
