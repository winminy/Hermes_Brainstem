from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.converters import NotionBlockConverter
from plugins.memory.hermes_memory.core.clock import FrozenClock


def test_notion_block_converter_renders_basic_rich_text_formatting(tmp_path: Path) -> None:
    sample = _load_fixture('notion_row_sample.json')
    converter = NotionBlockConverter(_config(tmp_path), clock=_clock())

    artifact = converter.convert_page(
        page=_page(sample),
        blocks=_blocks(sample),
        tags=('AI',),
    )

    assert '**bold**' in artifact.body
    assert '*italic*' in artifact.body
    assert '~~struck~~' in artifact.body
    assert '`inline`' in artifact.body
    assert '[docs](https://example.test/docs)' in artifact.body
    assert artifact.frontmatter.area.value == 'inbox'
    assert artifact.frontmatter.source == ('notion:page-123',)
    assert artifact.frontmatter.source_type.value == 'notion'


def test_notion_block_converter_replaces_heading_three_with_bullet(tmp_path: Path) -> None:
    sample = _load_fixture('notion_row_sample.json')
    converter = NotionBlockConverter(_config(tmp_path), clock=_clock())

    artifact = converter.convert_page(page=_page(sample), blocks=_blocks(sample), tags=('AI',))

    assert '- Deep details' in artifact.body
    assert '### Deep details' not in artifact.body


def test_notion_block_converter_preserves_wikilinks_and_file_embeds(tmp_path: Path) -> None:
    sample = _load_fixture('notion_row_sample.json')
    converter = NotionBlockConverter(_config(tmp_path), clock=_clock())

    artifact = converter.convert_page(page=_page(sample), blocks=_blocks(sample), tags=('AI',))

    assert '[[Project Atlas]]' in artifact.body
    assert '![[diagram.png]]' in artifact.body


def test_notion_block_converter_renders_code_equation_and_table_blocks(tmp_path: Path) -> None:
    sample = _load_fixture('notion_row_sample.json')
    converter = NotionBlockConverter(_config(tmp_path), clock=_clock())

    artifact = converter.convert_page(page=_page(sample), blocks=_blocks(sample), tags=('AI',))

    assert "```python\nprint('hello')\n```" in artifact.body
    assert '$$\nmc^2\n$$' in artifact.body
    assert '| Name | Value |' in artifact.body
    assert '| Alpha | 42 |' in artifact.body


def test_markdown_to_notion_blocks_round_trips_special_blocks(tmp_path: Path) -> None:
    converter = NotionBlockConverter(_config(tmp_path), clock=_clock())

    blocks = converter.document_to_notion_blocks(
        "---\nuuid: obs:20260424T0700\narea: inbox\ntype: memo\ntags:\n- AI\ndate: 2026-04-24\nupdated: 2026-04-24\nsource:\n- session:test\nsource_type: \"\"\nfile_type: md\n---\n\n# Reverse\n\n- Detail\n\n```python\nprint('hello')\n```\n\n| Name | Value |\n| --- | --- |\n| Alpha | 42 |\n"
    )

    assert blocks[0]['type'] == 'heading_1'
    assert blocks[1]['type'] == 'bulleted_list_item'
    assert blocks[2]['type'] == 'code'
    assert blocks[3]['type'] == 'table'
    assert len(cast(list[dict[str, Any]], blocks[3]['children'])) == 2


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills')
    return ConfigLayer.from_settings(settings)


def _clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 4, 24, 7, 0, tzinfo=timezone.utc))


def _load_fixture(name: str) -> dict[str, Any]:
    fixture_path = Path(__file__).with_name('fixtures') / name
    loaded = json.loads(fixture_path.read_text(encoding='utf-8'))
    return cast(dict[str, Any], loaded)


def _page(sample: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], sample['page'])


def _blocks(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], sample['blocks'])
