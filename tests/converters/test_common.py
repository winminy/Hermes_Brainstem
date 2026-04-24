from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.converters import ConverterCommon
from plugins.memory.hermes_memory.core.clock import FrozenClock


def test_frontmatter_round_trip_via_converter_common(tmp_path: Path) -> None:
    common = ConverterCommon(_config(tmp_path), clock=_clock())

    frontmatter = common.build_frontmatter(
        source=('session:test-session',),
        tags=('AI',),
        note_type='memo',
        area='inbox',
    )

    serialized = common.dump_frontmatter_yaml(frontmatter)
    restored = common.load_frontmatter_yaml(serialized)
    artifact = common.render_note(
        title='Round Trip Note',
        body='# Round Trip Note\n\n## Metadata\n- ok: true',
        source=('session:test-session',),
        tags=('AI',),
        uuid=frontmatter.uuid,
        date=frontmatter.date,
        updated=frontmatter.updated,
    )
    document = common.load_document(artifact.markdown)

    assert restored.ordered_dump() == frontmatter.ordered_dump()
    assert document.frontmatter.ordered_dump() == frontmatter.ordered_dump()
    assert artifact.logical_path == 'inbox/Round Trip Note.md'


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills')
    return ConfigLayer.from_settings(settings)


def _clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 4, 24, 7, 0, tzinfo=timezone.utc))
