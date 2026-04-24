from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type, datetime
from enum import Enum, StrEnum
import re
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import core_schema


UUID_PATTERN = r'^obs:[0-9]{8}T[0-9]{4}(-[0-9]+)?$'
DATE_PATTERN = r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
SOURCE_PATTERN = r'^(?:notion|web|session|attach|multi):.+$'


class Area(StrEnum):
    KNOWLEDGE = 'knowledge'
    INBOX = 'inbox'


class NoteType(StrEnum):
    PERSON = 'person'
    KNOWLEDGE = 'knowledge'
    TOOL = 'tool'
    SCHEDULE = 'schedule'
    PREFERENCE = 'preference'
    PROJECT = 'project'
    MEMO = 'memo'


BUILTIN_NOTE_TYPES = tuple(note_type.value for note_type in NoteType)


class NoteTypeValue(str):
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: object,
        _handler: object,
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(cls, core_schema.str_schema())

    @property
    def value(self) -> str:
        return str(self)


class SourceType(str, Enum):
    NOTION = 'notion'
    GDRIVE = 'gdrive'
    NONE = ''


class TagRegistryProtocol(Protocol):
    def validate(self, tags: tuple[str, ...]) -> tuple[str, ...]:
        ...

    def hierarchy_for(self, tag: str) -> tuple[str, ...]:
        ...


@dataclass(frozen=True, slots=True)
class TagHierarchy:
    tag: str
    parent_path: tuple[str, ...]


class FrontmatterModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    uuid: str = Field(pattern=UUID_PATTERN)
    area: Area
    type: NoteTypeValue
    tags: tuple[str, ...]
    date: str = Field(pattern=DATE_PATTERN)
    updated: str = Field(pattern=DATE_PATTERN)
    source: tuple[str, ...]
    source_type: SourceType
    file_type: str = Field(min_length=1)

    @field_validator('type', mode='before')
    @classmethod
    def validate_type(cls, value: object, info: ValidationInfo) -> NoteTypeValue:
        if not isinstance(value, str):
            raise ValueError('type must be a string')
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError('type must not be empty')
        allowed_types = _allowed_note_types_from_context(info)
        if normalized not in allowed_types:
            raise ValueError(f"type must be one of: {', '.join(allowed_types)}")
        return NoteTypeValue(normalized)

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, tags: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        registry = _tag_registry_from_context(info)
        validated = registry.validate(tags)
        for tag in validated:
            if not registry.hierarchy_for(tag):
                raise ValueError(f'tag is missing a hierarchy definition: {tag}')
        return validated

    @field_validator('date', 'updated', mode='before')
    @classmethod
    def normalize_date_strings(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date_type):
            return value.isoformat()
        return value

    @field_validator('source')
    @classmethod
    def validate_source(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            if not re.match(SOURCE_PATTERN, value):
                raise ValueError(f'invalid source entry: {value}')
            if value in seen:
                raise ValueError(f'duplicate source entry: {value}')
            seen.add(value)
            normalized.append(value)
        return tuple(normalized)

    @field_validator('file_type')
    @classmethod
    def normalize_file_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError('file_type must not be empty')
        return normalized

    @classmethod
    def from_data(
        cls,
        data: dict[str, object],
        *,
        tag_registry: TagRegistryProtocol,
        allowed_types: tuple[str, ...] | None = None,
    ) -> 'FrontmatterModel':
        return cls.model_validate(
            data,
            context={
                'tag_registry': tag_registry,
                'allowed_note_types': allowed_types or BUILTIN_NOTE_TYPES,
            },
        )

    def tag_hierarchy(self, registry: TagRegistryProtocol) -> tuple[TagHierarchy, ...]:
        return tuple(TagHierarchy(tag=tag, parent_path=registry.hierarchy_for(tag)) for tag in self.tags)

    def ordered_dump(self) -> dict[str, object]:
        return {
            'uuid': self.uuid,
            'area': self.area.value,
            'type': self.type.value,
            'tags': list(self.tags),
            'date': self.date,
            'updated': self.updated,
            'source': list(self.source),
            'source_type': self.source_type.value,
            'file_type': self.file_type,
        }


def _tag_registry_from_context(info: ValidationInfo) -> TagRegistryProtocol:
    context = info.context
    if not isinstance(context, dict):
        raise ValueError('tag registry validation context is required')
    registry = context.get('tag_registry')
    if registry is None:
        raise ValueError('tag registry validation context is required')
    if not hasattr(registry, 'validate') or not hasattr(registry, 'hierarchy_for'):
        raise ValueError('tag registry context does not implement the required protocol')
    return cast(TagRegistryProtocol, registry)


def _allowed_note_types_from_context(info: ValidationInfo) -> tuple[str, ...]:
    context = info.context
    if not isinstance(context, dict):
        return BUILTIN_NOTE_TYPES
    allowed = context.get('allowed_note_types')
    if not isinstance(allowed, tuple):
        return BUILTIN_NOTE_TYPES
    normalized = tuple(str(item).strip().lower() for item in allowed if str(item).strip())
    return normalized or BUILTIN_NOTE_TYPES
