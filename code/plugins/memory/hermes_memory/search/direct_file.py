from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
from typing import Literal

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel


@dataclass(frozen=True, slots=True)
class SearchFilters:
    area: str | None = None
    type: str | None = None
    tags: tuple[str, ...] = ()
    tag_match_mode: Literal['all', 'any'] = 'all'
    source_type: str | None = None
    file_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    updated_from: str | None = None
    updated_to: str | None = None

    def __post_init__(self) -> None:
        if self.tag_match_mode not in {'all', 'any'}:
            raise ValueError('tag_match_mode must be "all" or "any"')
        for value in (self.date_from, self.date_to, self.updated_from, self.updated_to):
            if value is not None:
                date.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class SearchEntryMetadata:
    title: str
    relative_path: str
    uuid: str
    area: str
    type: str
    tags: tuple[str, ...]
    date: str
    updated: str
    source: tuple[str, ...]
    source_type: str
    file_type: str


@dataclass(frozen=True, slots=True)
class SearchEntry:
    relative_path: str
    path: Path
    document: MarkdownDocument

    @property
    def title(self) -> str:
        return self.path.stem

    @property
    def frontmatter(self) -> FrontmatterModel:
        return self.document.frontmatter

    @property
    def body(self) -> str:
        return self.document.body

    def metadata(self) -> SearchEntryMetadata:
        frontmatter = self.frontmatter
        return SearchEntryMetadata(
            title=self.title,
            relative_path=self.relative_path,
            uuid=frontmatter.uuid,
            area=frontmatter.area.value,
            type=frontmatter.type.value,
            tags=frontmatter.tags,
            date=frontmatter.date,
            updated=frontmatter.updated,
            source=frontmatter.source,
            source_type=frontmatter.source_type.value,
            file_type=frontmatter.file_type,
        )


@dataclass(frozen=True, slots=True)
class SearchHit:
    score: float
    snippet: str
    metadata: SearchEntryMetadata
    origin: str


def read(relative_path: str | Path, *, config: ConfigLayer, vault_root: Path | None = None) -> SearchEntry:
    base = _require_vault_root(config, vault_root)
    path = _resolve_note_path(relative_path, vault_root=base, config=config)
    codec = FrontmatterCodec(config)
    document = codec.loads(path.read_text(encoding='utf-8'))
    return SearchEntry(relative_path=path.relative_to(base).as_posix(), path=path, document=document)


def search(
    query: str,
    *,
    config: ConfigLayer,
    filters: SearchFilters | None = None,
    vault_root: Path | None = None,
    top_k: int = 5,
) -> list[SearchHit]:
    resolved_filters = filters or SearchFilters()
    hits: list[SearchHit] = []
    for entry in _iter_entries(config=config, vault_root=vault_root):
        if not matches_filters(entry.frontmatter, resolved_filters):
            continue
        score = _lexical_score(entry, query)
        if query.strip() and score <= 0.0:
            continue
        hits.append(entry_to_hit(entry, query=query, score=score, origin='direct_file'))
    hits.sort(key=lambda hit: (-hit.score, hit.metadata.title.casefold(), hit.metadata.relative_path))
    return hits[: max(1, top_k)]


def matches_filters(frontmatter: FrontmatterModel, filters: SearchFilters) -> bool:
    if filters.area is not None and frontmatter.area.value != filters.area:
        return False
    if filters.type is not None and frontmatter.type.value != filters.type:
        return False
    if filters.source_type is not None and frontmatter.source_type.value != filters.source_type:
        return False
    if filters.file_type is not None and frontmatter.file_type != filters.file_type.casefold():
        return False
    if filters.tags:
        requested_tags = set(filters.tags)
        frontmatter_tags = set(frontmatter.tags)
        if filters.tag_match_mode == 'all' and not requested_tags.issubset(frontmatter_tags):
            return False
        if filters.tag_match_mode == 'any' and requested_tags.isdisjoint(frontmatter_tags):
            return False
    if not _matches_date_range(frontmatter.date, lower=filters.date_from, upper=filters.date_to):
        return False
    if not _matches_date_range(frontmatter.updated, lower=filters.updated_from, upper=filters.updated_to):
        return False
    return True


def entry_to_hit(entry: SearchEntry, *, query: str, score: float, origin: str) -> SearchHit:
    return SearchHit(
        score=max(0.0, float(score)),
        snippet=_build_snippet(entry, query),
        metadata=entry.metadata(),
        origin=origin,
    )


def _iter_entries(*, config: ConfigLayer, vault_root: Path | None) -> Iterator[SearchEntry]:
    base = _require_vault_root(config, vault_root)
    codec = FrontmatterCodec(config)
    for note_root in config.vault_spec.provider_managed_note_roots:
        root = base / note_root.rstrip('/')
        if not root.exists():
            continue
        for path in sorted(root.rglob('*.md')):
            if config.is_quarantined_path(path, vault_root=base):
                continue
            try:
                document = codec.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            yield SearchEntry(relative_path=path.relative_to(base).as_posix(), path=path, document=document)


def _resolve_note_path(candidate_path: str | Path, *, vault_root: Path, config: ConfigLayer) -> Path:
    candidate = Path(candidate_path)
    if candidate.suffix.lower() != '.md':
        raise ValueError('direct_file.read only supports markdown notes')
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (vault_root / candidate).resolve()
    base = vault_root.resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError('direct_file.read cannot escape the vault root') from exc
    if config.is_quarantined_path(resolved, vault_root=base):
        raise ValueError('quarantined documents are excluded from direct_file.read')
    allowed_roots = {root.rstrip('/') for root in config.vault_spec.provider_managed_note_roots}
    if not relative.parts or relative.parts[0] not in allowed_roots:
        raise ValueError('direct_file.read only allows provider-managed note roots')
    return resolved


def _lexical_score(entry: SearchEntry, query: str) -> float:
    if not query.strip():
        return 0.0
    terms = _query_terms(query)
    title_text = entry.title.casefold()
    body_text = entry.body.casefold()
    tag_text = ' '.join(entry.frontmatter.tags).casefold()
    meta_text = ' '.join(
        (
            entry.frontmatter.uuid,
            entry.frontmatter.area.value,
            entry.frontmatter.type.value,
            entry.frontmatter.date,
            entry.frontmatter.updated,
            entry.frontmatter.source_type.value,
            entry.frontmatter.file_type,
            *entry.frontmatter.source,
        )
    ).casefold()

    score = 0.0
    for term in terms:
        if term in title_text:
            score += 0.45
        if term in tag_text:
            score += 0.25
        if term in meta_text:
            score += 0.15
        if term in body_text:
            score += min(0.35, 0.08 * body_text.count(term))
    return min(1.0, score / len(terms))


def _build_snippet(entry: SearchEntry, query: str, *, width: int = 180) -> str:
    normalized_body = _normalize_whitespace(entry.body)
    if not normalized_body:
        return entry.title
    if not query.strip():
        return normalized_body[:width]
    lower_body = normalized_body.casefold()
    for term in _query_terms(query):
        index = lower_body.find(term)
        if index >= 0:
            start = max(0, index - (width // 3))
            end = min(len(normalized_body), index + width)
            snippet = normalized_body[start:end]
            if start > 0:
                snippet = f'…{snippet}'
            if end < len(normalized_body):
                snippet = f'{snippet}…'
            return snippet
    return normalized_body[:width]


def _query_terms(query: str) -> tuple[str, ...]:
    terms = tuple(token.casefold() for token in re.findall(r'\w+', query, flags=re.UNICODE) if token)
    if terms:
        return terms
    return (query.casefold(),)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def _matches_date_range(value: str, *, lower: str | None, upper: str | None) -> bool:
    if lower is not None and value < lower:
        return False
    if upper is not None and value > upper:
        return False
    return True


def _require_vault_root(config: ConfigLayer, vault_root: Path | None) -> Path:
    base = vault_root or config.settings.vault_root
    if base is None:
        raise ValueError('vault_root is required for search operations')
    return base


__all__ = [
    'SearchEntry',
    'SearchEntryMetadata',
    'SearchFilters',
    'SearchHit',
    'entry_to_hit',
    'matches_filters',
    'read',
    'search',
]
