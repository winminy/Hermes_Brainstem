from __future__ import annotations

from dataclasses import dataclass
import re

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.interpreter.meta_loader import MetaLoader

from .reduce import ReducedEntry


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    entrypoint: str
    area: str
    relative_path: str
    basename: str


@dataclass(frozen=True, slots=True)
class PersistProcessPolicy:
    default_path: str
    allowed_sources: tuple[str, ...]


class PipelineDispatcher:
    def __init__(self, config: ConfigLayer, *, meta_loader: MetaLoader | None = None) -> None:
        self._config = config
        self._meta_loader = meta_loader or MetaLoader(config)
        self._persist_process_policy = self._load_policy()

    def dispatch(self, entry: ReducedEntry, *, entrypoint: str = 'persist.process') -> DispatchDecision:
        if entrypoint != 'persist.process':
            raise ValueError(f'unsupported entrypoint: {entrypoint}')
        source_prefixes = {item.split(':', 1)[0] for item in entry.frontmatter.source}
        invalid_sources = sorted(source_prefixes.difference(self._persist_process_policy.allowed_sources))
        if invalid_sources:
            raise ValueError(f'entry source prefixes are not allowed for persist.process: {invalid_sources}')
        allowed_roots = {root.rstrip('/') for root in self._config.vault_spec.provider_managed_note_roots}
        preferred_area = entry.frontmatter.area.value
        default_root = self._persist_process_policy.default_path.rstrip('/')
        resolved_root = preferred_area if preferred_area in allowed_roots else default_root
        if resolved_root not in allowed_roots:
            raise ValueError(f'dispatch root is outside provider-managed note roots: {resolved_root}')
        basename = f'{_safe_basename(entry.title)}.md'
        return DispatchDecision(
            entrypoint=entrypoint,
            area=resolved_root,
            relative_path=f'{resolved_root}/{basename}',
            basename=basename,
        )

    def _load_policy(self) -> PersistProcessPolicy:
        document = self._meta_loader.get('self_reference/persist_policy.md')
        block = _extract_fenced_yaml(document.text)
        process_block_match = re.search(r'persist\.process:\n(?P<body>(?:\s{4}.+\n?)+)', block)
        if process_block_match is None:
            raise ValueError('persist.process policy block is required')
        process_block = process_block_match.group('body')
        default_match = re.search(r'default_path:\s*(?P<value>[^\n]+)', process_block)
        allowed_match = re.search(r'allowed_sources:\s*\[(?P<value>[^\]]*)\]', process_block)
        if default_match is None or allowed_match is None:
            raise ValueError('persist.process default_path and allowed_sources are required')
        default_path = default_match.group('value').strip()
        allowed_sources = tuple(
            item.strip()
            for item in allowed_match.group('value').split(',')
            if item.strip()
        )
        return PersistProcessPolicy(default_path=default_path, allowed_sources=allowed_sources)


def _safe_basename(title: str) -> str:
    candidate = title.strip().replace('/', '-').replace('\\', '-')
    candidate = candidate.strip().strip('.')
    return candidate or 'untitled'


def _extract_fenced_yaml(markdown: str) -> str:
    match = re.search(r'```yaml\n(?P<body>.*?)\n```', markdown, re.DOTALL)
    if match is None:
        raise ValueError('yaml fenced block not found')
    return match.group('body')
