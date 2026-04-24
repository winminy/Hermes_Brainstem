from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate, suggest_links


class FakeLightRAG:
    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate]:
        assert text == 'context'
        assert top_k == 8
        return [
            LightRAGCandidate(title='Alpha', path='/vault/knowledge/Alpha.md', score=0.9, type='knowledge'),
            LightRAGCandidate(title='Hidden', path='/vault/_quarantine/2026-04/Hidden.md', score=0.95, type='memo'),
            LightRAGCandidate(title='Beta', path='/vault/inbox/Beta.md', score=0.8, type='memo'),
            LightRAGCandidate(title='Gamma', path='/vault/knowledge/Gamma.md', score=0.7, type='unsupported'),
            LightRAGCandidate(title='Alpha', path='/vault/knowledge/Alpha.md', score=0.6, type='knowledge'),
        ]


def test_suggest_links_filters_quarantine_and_limits_to_two() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings(vault_root=Path('/vault')))

    links = suggest_links('context', FakeLightRAG(), config=config)

    assert links == ['[[Alpha]]', '[[Beta]]']
