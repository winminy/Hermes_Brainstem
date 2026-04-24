from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.converters import ConversationBinaryConverter
from plugins.memory.hermes_memory.core.clock import FrozenClock


def test_conversation_binary_converter_creates_metadata_only_inbox_note(tmp_path: Path) -> None:
    sample = _load_fixture('conversation_sample.json')
    converter = ConversationBinaryConverter(_config(tmp_path), clock=_clock())

    artifact = converter.convert_session(
        session_id=cast(str, sample['session_id']),
        conversation_history=sample['conversation_history'],
        model=cast(str, sample['model']),
        platform=cast(str, sample['platform']),
        tags=('AI',),
    )

    assert artifact.frontmatter.source == ('session:sess-42',)
    assert artifact.frontmatter.area.value == 'inbox'
    assert 'This raw transcript must not be persisted.' not in artifact.body
    assert '- message_count: 2' in artifact.body
    assert '- attachment_count: 2' in artifact.body
    assert '- ![[screenshot.png]]' in artifact.body
    assert '- ![[spec.pdf]]' in artifact.body


def test_conversation_binary_converter_extracts_binary_artifacts(tmp_path: Path) -> None:
    sample = _load_fixture('conversation_sample.json')
    converter = ConversationBinaryConverter(_config(tmp_path), clock=_clock())

    artifacts = converter.extract_attachments(
        session_id=cast(str, sample['session_id']),
        conversation_history=sample['conversation_history'],
    )

    assert [artifact.filename for artifact in artifacts] == ['screenshot.png', 'spec.pdf']
    assert [artifact.logical_path for artifact in artifacts] == [
        'attachments/2026/04/screenshot.png',
        'attachments/2026/04/spec.pdf',
    ]
    assert artifacts[0].payload == b'image-bytes'
    assert artifacts[1].payload == b'%PDF-1.7'


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills')
    return ConfigLayer.from_settings(settings)


def _clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 4, 24, 7, 0, tzinfo=timezone.utc))


def _load_fixture(name: str) -> dict[str, Any]:
    fixture_path = Path(__file__).with_name('fixtures') / name
    loaded = json.loads(fixture_path.read_text(encoding='utf-8'))
    return cast(dict[str, Any], loaded)
