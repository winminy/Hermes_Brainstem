from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.logger import configure_logging
from plugins.memory.hermes_memory.core.wikilink import LightRAGCandidate

from . import direct_file
from .direct_file import SearchFilters, SearchHit


class SemanticSearchBackend(Protocol):
    def query_related(self, text: str, *, top_k: int) -> Sequence[LightRAGCandidate | Mapping[str, Any]]:
        ...


def search(
    query: str,
    backend: SemanticSearchBackend,
    *,
    config: ConfigLayer,
    filters: SearchFilters | None = None,
    vault_root: Path | None = None,
    top_k: int = 5,
) -> list[SearchHit]:
    resolved_top_k = max(1, top_k)
    resolved_filters = filters or SearchFilters()
    logger = configure_logging(config.settings)

    try:
        raw_candidates = backend.query_related(query, top_k=max(resolved_top_k * 3, resolved_top_k))
    except Exception as exc:
        logger.warning('semantic.search.lightrag_unavailable', reason=str(exc))
        return direct_file.search(query, config=config, filters=resolved_filters, vault_root=vault_root, top_k=resolved_top_k)

    hits: list[SearchHit] = []
    seen_paths: set[str] = set()
    for raw_candidate in raw_candidates:
        candidate = _coerce_candidate(raw_candidate)
        if not candidate.path or config.is_quarantined_path(candidate.path, vault_root=vault_root):
            continue
        entry = _read_candidate(candidate.path, config=config, vault_root=vault_root)
        if entry is None:
            continue
        if entry.relative_path in seen_paths:
            continue
        if not direct_file.matches_filters(entry.frontmatter, resolved_filters):
            continue
        hits.append(direct_file.entry_to_hit(entry, query=query, score=candidate.score, origin='semantic'))
        seen_paths.add(entry.relative_path)

    if len(hits) < resolved_top_k:
        for hit in direct_file.search(
            query,
            config=config,
            filters=resolved_filters,
            vault_root=vault_root,
            top_k=resolved_top_k * 2,
        ):
            if hit.metadata.relative_path in seen_paths:
                continue
            hits.append(hit)
            seen_paths.add(hit.metadata.relative_path)
            if len(hits) >= resolved_top_k:
                break

    hits.sort(key=lambda hit: (-hit.score, hit.metadata.title.casefold(), hit.metadata.relative_path))
    return hits[:resolved_top_k]


def _coerce_candidate(candidate: LightRAGCandidate | Mapping[str, Any]) -> LightRAGCandidate:
    if isinstance(candidate, LightRAGCandidate):
        return candidate
    title = candidate.get('title', '')
    path = candidate.get('path', '')
    score = candidate.get('score', 0.0)
    note_type = candidate.get('type', 'knowledge')
    if not isinstance(title, str) or not isinstance(path, str) or not isinstance(note_type, str):
        raise ValueError('LightRAG candidate title/path/type must be strings')
    if isinstance(score, bool) or not isinstance(score, int | float):
        raise ValueError('LightRAG candidate score must be numeric')
    return LightRAGCandidate(title=title, path=path, score=float(score), type=note_type)


def _read_candidate(candidate_path: str, *, config: ConfigLayer, vault_root: Path | None) -> direct_file.SearchEntry | None:
    base = vault_root or config.settings.vault_root
    if base is None:
        raise ValueError('vault_root is required for semantic search')
    candidate = Path(candidate_path)
    try:
        relative = candidate.resolve().relative_to(base.resolve()) if candidate.is_absolute() else candidate
    except ValueError:
        return None
    try:
        return direct_file.read(relative, config=config, vault_root=base)
    except (FileNotFoundError, ValueError, OSError):
        return None


__all__ = ['SemanticSearchBackend', 'search']
