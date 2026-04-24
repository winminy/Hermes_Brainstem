from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.hooks.quarantine_sweep import run_quarantine_sweep


class FakeServices:
    def __init__(self, config: ConfigLayer) -> None:
        self.config = config


def test_quarantine_sweep_moves_invalid_entry_into_quarantine_bucket(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_valid_note(config, tmp_path, area='knowledge', title='clean-note')
    invalid_path = tmp_path / 'inbox' / 'expired-entry.md'
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(
        '---\n'
        'uuid: obs:20260424T0642\n'
        'area: system\n'
        'type: memo\n'
        'tags: []\n'
        'date: 2026-04-24\n'
        'updated: 2026-04-24\n'
        'source:\n'
        '- session:expired\n'
        'source_type: ""\n'
        'file_type: md\n'
        '---\n\n'
        'Invalid body\n',
        encoding='utf-8',
    )

    result = run_quarantine_sweep(services=cast(Any, FakeServices(config)), vault_root=tmp_path)

    quarantined = next(entry for entry in result.entries if entry.relative_path == 'inbox/expired-entry.md')
    clean = next(entry for entry in result.entries if entry.relative_path == 'knowledge/clean-note.md')
    assert quarantined.status == 'quarantined'
    assert quarantined.quarantine_path is not None
    assert Path(quarantined.quarantine_path).exists()
    assert not invalid_path.exists()
    reason_path = Path(quarantined.quarantine_path + '.reason.txt')
    assert reason_path.exists()
    assert clean.status == 'clean'
    audit_path = tmp_path / 'inbox' / '.hermes-quarantine-sweep-audit.jsonl'
    assert audit_path.exists()
    assert 'expired-entry.md' in audit_path.read_text(encoding='utf-8')


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', timezone='UTC', log_level='INFO')
    return ConfigLayer.from_settings(settings)


def _write_valid_note(config: ConfigLayer, vault_root: Path, *, area: str, title: str) -> None:
    codec = FrontmatterCodec(config)
    frontmatter = FrontmatterModel.from_data(
        {
            'uuid': 'obs:20260424T0643',
            'area': area,
            'type': 'memo',
            'tags': [],
            'date': '2026-04-24',
            'updated': '2026-04-24',
            'source': ['session:valid'],
            'source_type': '',
            'file_type': 'md',
        },
        tag_registry=config.tag_registry,
    )
    path = vault_root / area / f'{title}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(codec.dumps(MarkdownDocument(frontmatter=frontmatter, body='# Valid note')), encoding='utf-8')
