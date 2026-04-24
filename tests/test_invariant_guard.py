from __future__ import annotations

import pytest

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec
from plugins.memory.hermes_memory.core.invariant_guard import GuardedWriter, InvariantViolationError


@pytest.fixture()
def codec() -> FrontmatterCodec:
    return FrontmatterCodec(ConfigLayer.from_settings(HermesMemorySettings()))


def test_guarded_writer_blocks_immutable_field_changes(codec: FrontmatterCodec) -> None:
    existing = codec.loads("""---
uuid: obs:20260423T1039
area: knowledge
type: memo
tags:
  - AI
date: 2026-04-23
updated: 2026-04-23
source:
  - session:test
source_type: ""
file_type: md
---

Original
""")
    candidate = codec.loads("""---
uuid: obs:20260423T1040
area: knowledge
type: memo
tags:
  - AI
date: 2026-04-23
updated: 2026-04-24
source:
  - session:test
source_type: ""
file_type: md
---

Changed
""")

    writer = GuardedWriter(lambda document: document.body)

    with pytest.raises(InvariantViolationError):
        writer.write(candidate, existing=existing)


def test_guarded_writer_allows_mutable_field_updates(codec: FrontmatterCodec) -> None:
    existing = codec.loads("""---
uuid: obs:20260423T1039
area: knowledge
type: memo
tags:
  - AI
date: 2026-04-23
updated: 2026-04-23
source:
  - session:test
source_type: ""
file_type: md
---

Original
""")
    candidate = codec.loads("""---
uuid: obs:20260423T1039
area: knowledge
type: memo
tags:
  - AI
date: 2026-04-23
updated: 2026-04-24
source:
  - session:test
source_type: ""
file_type: md
---

Changed
""")

    writer = GuardedWriter(lambda document: document.body)

    assert writer.write(candidate, existing=existing) == 'Changed'
