from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from jsonschema import validate

from plugins.memory.hermes_memory.backends.llm import StructuredLLMBackend, StructuredLLMRequest, build_structured_llm
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.clock import Clock, SystemClock
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.core.uuid_gen import UUIDGenerator
from plugins.memory.hermes_memory.interpreter.meta_loader import MetaLoader
from plugins.memory.hermes_memory.interpreter.schema_builder import SchemaBuilder

from .map import MappedNotionEntry


@dataclass(frozen=True, slots=True)
class ReducedEntry:
    datasource: str
    source_page_id: str
    title: str
    body: str
    frontmatter: FrontmatterModel
    markdown: str
    raw_page: Mapping[str, Any]

    def document(self) -> MarkdownDocument:
        return MarkdownDocument(frontmatter=self.frontmatter, body=self.body)


class StructuredEntryReducer:
    def __init__(
        self,
        *,
        config: ConfigLayer,
        llm_backend: StructuredLLMBackend | None = None,
        schema_builder: SchemaBuilder | None = None,
        meta_loader: MetaLoader | None = None,
        clock: Clock | None = None,
        uuid_generator: UUIDGenerator | None = None,
    ) -> None:
        self._config = config
        self._meta_loader = meta_loader or MetaLoader(config)
        self._schema_builder = schema_builder or SchemaBuilder(config, meta_loader=self._meta_loader)
        self._llm_backend = llm_backend or build_structured_llm(config)
        self._clock = clock or SystemClock(config.settings.timezone)
        self._uuid_generator = uuid_generator or UUIDGenerator(clock=self._clock)
        self._codec = FrontmatterCodec(config)

    def reduce(self, mapped: MappedNotionEntry) -> ReducedEntry:
        seed_uuid = self._uuid_generator.generate()
        seed_frontmatter = mapped.seed_frontmatter(uuid=seed_uuid)
        schema = self._schema_builder.build_entry_schema()
        request = StructuredLLMRequest(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(mapped, seed_frontmatter=seed_frontmatter),
            output_schema=schema,
            tools=(self._schema_builder.build_anthropic_tool(),),
        )
        raw_response = dict(self._llm_backend.generate(request))
        validate(instance=raw_response, schema=schema)

        raw_title = raw_response.get('title')
        raw_body = raw_response.get('body')
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise ValueError('reduce.title must be a non-empty string')
        if not isinstance(raw_body, str):
            raise ValueError('reduce.body must be a string')

        normalized_body = _normalize_markdown(raw_body)
        final_payload = {
            'title': raw_title.strip(),
            'body': normalized_body,
            'frontmatter': seed_frontmatter,
        }
        validate(instance=final_payload, schema=schema)
        frontmatter = FrontmatterModel.from_data(seed_frontmatter, tag_registry=self._config.tag_registry)
        markdown = self._codec.dumps(MarkdownDocument(frontmatter=frontmatter, body=normalized_body))
        return ReducedEntry(
            datasource=mapped.datasource,
            source_page_id=mapped.source_page_id,
            title=raw_title.strip(),
            body=normalized_body,
            frontmatter=frontmatter,
            markdown=markdown,
            raw_page=mapped.raw_page,
        )

    def _system_prompt(self) -> str:
        vault_spec = self._meta_loader.get('vault_spec.md').body
        tags = self._meta_loader.get('TAGS.md').body
        return (
            'You convert mapped source chunks into an Obsidian-native markdown note. '
            'Return a JSON object that matches the provided schema exactly. '
            'Preserve the supplied frontmatter seed values exactly. '
            'Use only # and ## headings, convert deeper headings to bullets, and never emit blockquotes.\n\n'
            f'[vault_spec]\n{vault_spec}\n\n[TAGS]\n{tags}'
        )

    def _user_prompt(self, mapped: MappedNotionEntry, *, seed_frontmatter: Mapping[str, object]) -> str:
        payload = {
            'datasource': mapped.datasource,
            'source_page_id': mapped.source_page_id,
            'title_hint': mapped.title,
            'seed_frontmatter': dict(seed_frontmatter),
            'tag_candidates': list(mapped.tag_candidates),
            'chunks': mapped.chunk_payload(),
        }
        return 'Generate one Hermes vault entry for this mapped payload. PAYLOAD:\n' + json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_markdown(body: str) -> str:
    lines: list[str] = []
    for raw_line in body.splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith('>'):
            content = stripped.lstrip('>').strip()
            lines.append(f'- {content}' if content else '-')
            continue
        if stripped.startswith('###'):
            content = stripped.lstrip('#').strip()
            lines.append(f'- {content}' if content else '-')
            continue
        lines.append(raw_line.rstrip())
    return '\n'.join(lines).strip()
