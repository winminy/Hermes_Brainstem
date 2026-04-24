from __future__ import annotations

from datetime import date
from pathlib import Path

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings


def test_config_layer_loads_bundled_resources_and_quarantine_paths() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings(vault_root=Path('/vault')))

    assert 'project' in config.tag_registry.tags
    assert config.tag_registry.hierarchy_for('AI') == ('topic', 'technology')
    assert config.vault_spec.type_values == ('person', 'knowledge', 'tool', 'schedule', 'preference', 'project', 'memo')
    assert config.quarantine_root() == Path('/vault/_quarantine')
    assert config.quarantine_bucket(date(2026, 4, 23)) == Path('/vault/_quarantine/2026-04')
    assert config.is_quarantined_path('/vault/_quarantine/2026-04/bad.md') is True
    assert config.is_quarantined_path('/vault/knowledge/good.md') is False
