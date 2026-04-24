from __future__ import annotations

import pytest
from pydantic import ValidationError

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec
from plugins.memory.hermes_memory.core.models import FrontmatterModel


@pytest.fixture()
def codec() -> FrontmatterCodec:
    return FrontmatterCodec(ConfigLayer.from_settings(HermesMemorySettings()))


def test_frontmatter_loads_and_dumps_preserving_field_order(codec: FrontmatterCodec) -> None:
    text = """---
uuid: obs:20260423T1039
area: knowledge
type: memo
tags:
  - AI
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - session:test
source_type: ""
file_type: md
---

Body text
"""

    document = codec.loads(text)
    dumped = codec.dumps(document)
    lines = dumped.splitlines()

    assert document.frontmatter.area.value == 'knowledge'
    assert document.frontmatter.tags == ('AI', '개발')
    assert lines[:15] == [
        '---',
        'uuid: obs:20260423T1039',
        'area: knowledge',
        'type: memo',
        'tags:',
        '- AI',
        '- 개발',
        'date: 2026-04-23',
        'updated: 2026-04-23',
        'source:',
        '- session:test',
        'source_type: ""',
        'file_type: md',
        '---',
        '',
    ]
    assert dumped.endswith('Body text\n')


def test_frontmatter_rejects_unregistered_tag(codec: FrontmatterCodec) -> None:
    text = """---
uuid: obs:20260423T1039
area: knowledge
type: memo
tags:
  - 없는태그
date: 2026-04-23
updated: 2026-04-23
source:
  - session:test
source_type: ""
file_type: md
---

Body text
"""

    with pytest.raises(ValidationError):
        codec.loads(text)


def test_frontmatter_rejects_invalid_area(codec: FrontmatterCodec) -> None:
    with pytest.raises(ValidationError):
        FrontmatterModel.from_data(
            {
                'uuid': 'obs:20260423T1039',
                'area': 'system',
                'type': 'memo',
                'tags': ['AI'],
                'date': '2026-04-23',
                'updated': '2026-04-23',
                'source': ['session:test'],
                'source_type': '',
                'file_type': 'md',
            },
            tag_registry=codec._config.tag_registry,
        )
