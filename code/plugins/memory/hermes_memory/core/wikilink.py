from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from plugins.memory.hermes_memory.config.layer import ConfigLayer


@dataclass(frozen=True, slots=True)
class LightRAGCandidate:
    title: str
    path: str
    score: float
    type: str

    @property
    def basename(self) -> str:
        if self.title:
            return self.title
        return Path(self.path).stem


class LightRAGQueryBackend(Protocol):
    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate | Mapping[str, Any]]:
        ...


@dataclass(frozen=True, slots=True)
class WikilinkPolicy:
    max_links: int
    top_k: int
    score_threshold: float


def suggest_links(
    text: str,
    backend: LightRAGQueryBackend,
    *,
    config: ConfigLayer,
    policy: WikilinkPolicy | None = None,
) -> list[str]:
    resolved_policy = policy or WikilinkPolicy(
        max_links=config.settings.wikilink_max_links,
        top_k=config.settings.wikilink_top_k,
        score_threshold=config.settings.wikilink_score_threshold,
    )
    raw_candidates = backend.query_related(text, top_k=resolved_policy.top_k)
    filtered: list[LightRAGCandidate] = []
    for raw_candidate in raw_candidates:
        candidate = _coerce_candidate(raw_candidate)
        if candidate.score < resolved_policy.score_threshold:
            continue
        if candidate.type not in set(config.allowed_note_types):
            continue
        if config.is_quarantined_path(candidate.path):
            continue
        filtered.append(candidate)
    filtered.sort(key=lambda candidate: (-candidate.score, candidate.basename.casefold()))

    links: list[str] = []
    seen: set[str] = set()
    for candidate in filtered:
        basename = candidate.basename
        if basename in seen:
            continue
        seen.add(basename)
        links.append(f'[[{basename}]]')
        if len(links) >= resolved_policy.max_links:
            break
    return links


def _coerce_candidate(candidate: LightRAGCandidate | Mapping[str, Any]) -> LightRAGCandidate:
    if isinstance(candidate, LightRAGCandidate):
        return candidate
    title = candidate.get('title', '')
    path = candidate.get('path', '')
    score = candidate.get('score', 0.0)
    note_type = candidate.get('type', '')
    if not isinstance(title, str) or not isinstance(path, str) or not isinstance(note_type, str):
        raise ValueError('LightRAG candidate title/path/type must be strings')
    if isinstance(score, bool) or not isinstance(score, int | float):
        raise ValueError('LightRAG candidate score must be numeric')
    return LightRAGCandidate(title=title, path=path, score=float(score), type=note_type)
