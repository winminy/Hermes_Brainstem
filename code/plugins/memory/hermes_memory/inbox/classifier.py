from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import json

from jsonschema import validate

from plugins.memory.hermes_memory.backends.llm import StructuredLLMBackend, StructuredLLMRequest, build_structured_llm
from plugins.memory.hermes_memory.config.layer import ConfigLayer
from plugins.memory.hermes_memory.core.frontmatter import MarkdownDocument
from plugins.memory.hermes_memory.core.models import FrontmatterModel


ClassificationStatus = Literal['success', 'ambiguous', 'invalid']


@dataclass(frozen=True, slots=True)
class InboxClassification:
    status: ClassificationStatus
    title: str
    body: str
    area: str | None
    note_type: str | None
    tags: tuple[str, ...]
    reason: str | None
    reason_tag: str | None


class InboxClassifier:
    def __init__(self, config: ConfigLayer, *, llm_backend: StructuredLLMBackend | None = None) -> None:
        self._config = config
        self._llm_backend = llm_backend or build_structured_llm(config)

    def classify(self, *, title: str, document: MarkdownDocument) -> InboxClassification:
        schema = self._build_schema()
        request = StructuredLLMRequest(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(title=title, document=document),
            output_schema=schema,
            tools=(),
        )
        raw_response = dict(self._llm_backend.generate(request))
        validate(instance=raw_response, schema=schema)

        status = raw_response['status']
        if not isinstance(status, str):
            raise ValueError('classifier status must be a string')
        payload_title = raw_response.get('title', title)
        payload_body = raw_response.get('body', document.body)
        if not isinstance(payload_title, str) or not payload_title.strip():
            raise ValueError('classifier title must be a non-empty string')
        if not isinstance(payload_body, str):
            raise ValueError('classifier body must be a string')

        if status == 'success':
            classification = raw_response.get('classification')
            if not isinstance(classification, dict):
                raise ValueError('classifier success response must include classification')
            area = classification.get('area')
            note_type = classification.get('type')
            raw_tags = classification.get('tags', [])
            if not isinstance(area, str) or not isinstance(note_type, str) or not isinstance(raw_tags, list):
                raise ValueError('classifier success classification must include area/type/tags')
            validated_tags = self._config.tag_registry.validate(tuple(str(tag) for tag in raw_tags))
            FrontmatterModel.from_data(
                {
                    'uuid': document.frontmatter.uuid,
                    'area': area,
                    'type': note_type,
                    'tags': list(validated_tags),
                    'date': document.frontmatter.date,
                    'updated': document.frontmatter.updated,
                    'source': list(document.frontmatter.source),
                    'source_type': document.frontmatter.source_type.value,
                    'file_type': document.frontmatter.file_type,
                },
                tag_registry=self._config.tag_registry,
                allowed_types=self._config.allowed_note_types,
            )
            return InboxClassification(
                status='success',
                title=payload_title.strip(),
                body=payload_body.strip(),
                area=area,
                note_type=note_type,
                tags=validated_tags,
                reason=self._optional_string(raw_response.get('reason')),
                reason_tag=self._optional_string(raw_response.get('reason_tag')),
            )

        reason = self._optional_string(raw_response.get('reason'))
        reason_tag = self._optional_string(raw_response.get('reason_tag'))
        if reason is None or reason_tag is None:
            raise ValueError('ambiguous/invalid classifier responses require reason and reason_tag')
        if status == 'ambiguous':
            return InboxClassification(
                status='ambiguous',
                title=payload_title.strip(),
                body=payload_body.strip(),
                area=None,
                note_type=None,
                tags=(),
                reason=reason,
                reason_tag=reason_tag,
            )
        if status == 'invalid':
            return InboxClassification(
                status='invalid',
                title=payload_title.strip(),
                body=payload_body.strip(),
                area=None,
                note_type=None,
                tags=(),
                reason=reason,
                reason_tag=reason_tag,
            )
        raise ValueError(f'unsupported classifier status: {status}')

    def _build_schema(self) -> dict[str, object]:
        type_values = list(self._config.vault_spec.type_values)
        area_values = list(self._config.vault_spec.area_values)
        tag_values = list(self._config.tag_registry.tags)
        reason_tag_schema: dict[str, object] = {
            'type': 'string',
            'pattern': r'^[a-z0-9][a-z0-9-]{1,63}$',
        }
        return {
            'type': 'object',
            'additionalProperties': False,
            'required': ['status', 'title', 'body'],
            'properties': {
                'status': {'type': 'string', 'enum': ['success', 'ambiguous', 'invalid']},
                'title': {'type': 'string', 'minLength': 1},
                'body': {'type': 'string'},
                'classification': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['area', 'type', 'tags'],
                    'properties': {
                        'area': {'type': 'string', 'enum': area_values},
                        'type': {'type': 'string', 'enum': type_values},
                        'tags': {
                            'type': 'array',
                            'items': {'type': 'string', 'enum': tag_values},
                            'uniqueItems': True,
                        },
                    },
                },
                'reason': {'type': 'string'},
                'reason_tag': reason_tag_schema,
            },
            'allOf': [
                {
                    'if': {'properties': {'status': {'const': 'success'}}},
                    'then': {'required': ['classification']},
                },
                {
                    'if': {'properties': {'status': {'enum': ['ambiguous', 'invalid']}}},
                    'then': {'required': ['reason', 'reason_tag']},
                },
            ],
        }

    def _system_prompt(self) -> str:
        return (
            'Classify one Hermes inbox note using the bundled vault specification and tag registry. '
            'Use only the allowed type, area, and tag values. '
            'Return success only when the note can graduate directly to knowledge. '
            'Return ambiguous when human confirmation is still required. '
            'Return invalid when the note must be quarantined.\n\n'
            f'[vault_spec]\n{self._config.resources.vault_spec_markdown}\n\n'
            f'[TAGS]\n{self._config.resources.tags_markdown}'
        )

    def _user_prompt(self, *, title: str, document: MarkdownDocument) -> str:
        payload = {
            'title': title,
            'frontmatter': document.frontmatter.ordered_dump(),
            'body': document.body,
        }
        return 'Classify this inbox note. PAYLOAD:\n' + json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('expected a string value')
        stripped = value.strip()
        return stripped or None
