from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.interpreter.meta_loader import MetaLoader, REQUIRED_META_FILES


def test_meta_loader_loads_required_docs_and_detects_reload(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[2] / 'code' / 'plugins' / 'memory' / 'hermes_memory' / 'config' / 'resources'
    package_root = tmp_path / 'temp_resources'
    package_root.mkdir(parents=True)
    (package_root / '__init__.py').write_text('', encoding='utf-8')
    for relative_path in REQUIRED_META_FILES:
        target = package_root / '_system' / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((source_root / '_system' / relative_path).read_text(encoding='utf-8'), encoding='utf-8')

    monkeypatch.syspath_prepend(str(tmp_path))
    settings = HermesMemorySettings(resource_package='temp_resources')
    config = ConfigLayer.from_settings(settings)
    loader = MetaLoader(config)

    changed = loader.reload()
    assert changed == tuple(sorted(REQUIRED_META_FILES))
    assert loader.get('vault_spec.md').frontmatter['uuid'].startswith('obs:')

    tags_path = package_root / '_system' / 'TAGS.md'
    tags_path.write_text(tags_path.read_text(encoding='utf-8') + '\n<!-- changed -->\n', encoding='utf-8')
    assert loader.reload() == ('TAGS.md',)
