from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.pipeline import PersistProcessPipeline, ReducedEntry

from .classifier import InboxClassification


@dataclass(frozen=True, slots=True)
class GraduationResult:
    status: str
    knowledge_path: str | None
    removed_inbox_path: str | None


class InboxGraduator:
    def __init__(self, config: ConfigLayer, *, pipeline: PersistProcessPipeline) -> None:
        self._config = config
        self._pipeline = pipeline
        self._codec = FrontmatterCodec(config)

    def graduate(
        self,
        *,
        entry_path: Path,
        document: MarkdownDocument,
        title: str,
        classification: InboxClassification,
        vault_root: Path,
        dry_run: bool = False,
    ) -> GraduationResult:
        if classification.status != 'success':
            raise ValueError('only successful classifications can graduate')
        if classification.area != 'knowledge':
            raise ValueError(f'successful graduation must target knowledge, got {classification.area!r}')
        if classification.note_type is None:
            raise ValueError('successful graduation requires note_type')

        frontmatter_payload = document.frontmatter.ordered_dump()
        frontmatter_payload['area'] = classification.area
        frontmatter_payload['type'] = classification.note_type
        frontmatter_payload['tags'] = list(classification.tags)
        graduated_frontmatter = FrontmatterModel.from_data(
            frontmatter_payload,
            tag_registry=self._config.tag_registry,
            allowed_types=self._config.allowed_note_types,
        )
        reduced = ReducedEntry(
            datasource='inbox',
            source_page_id=graduated_frontmatter.uuid,
            title=classification.title or title,
            body=classification.body,
            frontmatter=graduated_frontmatter,
            markdown=self._codec.dumps(MarkdownDocument(frontmatter=graduated_frontmatter, body=classification.body)),
            raw_page={'inbox_path': str(entry_path)},
        )
        ignored_paths: tuple[str, ...] = ()
        try:
            ignored_paths = (entry_path.relative_to(vault_root).as_posix(),)
        except ValueError:
            ignored_paths = ()
        commit_result = self._pipeline.commit_reduced_entry(
            reduced,
            vault_root=vault_root,
            dry_run=dry_run,
            ignore_relative_paths=ignored_paths,
        )
        relative_path = commit_result.relative_path
        if relative_path is None or not relative_path.startswith('knowledge/'):
            raise ValueError(f'graduation wrote to an invalid path: {relative_path!r}')
        if not dry_run and entry_path.exists():
            entry_path.unlink()
        removed_inbox_path = None if dry_run else str(entry_path)
        return GraduationResult(
            status=commit_result.status,
            knowledge_path=relative_path,
            removed_inbox_path=removed_inbox_path,
        )
