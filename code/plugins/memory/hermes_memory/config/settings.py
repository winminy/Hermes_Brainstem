from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, YamlConfigSettingsSource

from plugins.memory.hermes_memory.core.models import BUILTIN_NOTE_TYPES


_DEFAULT_CONFIG_PATH = Path('config.yaml')

SUPPORTED_NOTION_SYNC_PROPERTY_TYPES: tuple[str, ...] = (
    'title',
    'rich_text',
    'number',
    'select',
    'multi_select',
    'status',
    'date',
    'person',
    'checkbox',
    'url',
    'email',
    'phone_number',
    'files',
    'relation',
    'created_time',
    'last_edited_time',
    'created_by',
    'last_edited_by',
    'formula',
    'rollup',
)


class SyncProperty(BaseModel):
    name: str
    type: str

    @field_validator('name', mode='before')
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or value
        return value

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in SUPPORTED_NOTION_SYNC_PROPERTY_TYPES:
            supported = ', '.join(SUPPORTED_NOTION_SYNC_PROPERTY_TYPES)
            raise ValueError(f'unsupported notion sync property type: {normalized}. Supported: {supported}')
        return normalized


class NotionDatabaseConfig(BaseModel):
    name: str
    id: str
    type: str | None = None
    sync_properties: list[SyncProperty] | None = None
    mapping_property: str | None = None
    mapping: dict[str, str | None] | None = None
    filter: dict[str, Any] | None = None
    scan_mode: str | None = 'daily_auto'

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

    @field_validator('mapping', mode='before')
    @classmethod
    def normalize_mapping(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, dict):
            return value
        normalized: dict[str, str | None] = {}
        for key, raw_target in value.items():
            mapping_key = str(key).strip()
            if raw_target is None:
                normalized[mapping_key] = None
                continue
            if isinstance(raw_target, str):
                target = raw_target.strip().lower()
                normalized[mapping_key] = target or None
                continue
            normalized[mapping_key] = str(raw_target).strip().lower() or None
        return normalized

    @field_validator('scan_mode', mode='before')
    @classmethod
    def normalize_scan_mode(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @model_validator(mode='after')
    def validate_mapping_mode(self) -> 'NotionDatabaseConfig':
        has_type = self.type is not None
        has_mapping_property = self.mapping_property is not None
        has_mapping = self.mapping is not None
        if has_type and (has_mapping_property or has_mapping):
            raise ValueError('notion database config cannot define both type and mapping-based routing')
        if has_mapping_property != has_mapping:
            raise ValueError('mapping_property and mapping must be provided together')
        if not has_type and not has_mapping_property:
            raise ValueError('notion database config must define either type or mapping_property + mapping')
        return self


class NotionSettings(BaseModel):
    api_key: str | None = None
    service_name: str = 'notion'
    env_vars: tuple[str, ...] = ('NOTION_API_KEY', 'HERMES_MEMORY_NOTION_API_KEY')
    timeout_seconds: float = Field(default=30.0, gt=0)
    page_size: int = Field(default=100, ge=1, le=100)
    databases: list[NotionDatabaseConfig] = Field(default_factory=list)


class EmbeddingAPISettings(BaseModel):
    provider: str = 'openai'
    model: str = 'text-embedding-3-small'
    base_url: str | None = None
    api_key: str | None = None
    service_name: str = 'openai'
    env_vars: tuple[str, ...] = ('OPENAI_API_KEY', 'HERMES_MEMORY_OPENAI_API_KEY', 'HERMES_MEMORY_EMBEDDING_API_KEY')
    dimensions: int | None = Field(default=None, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0)


class EmbeddingLocalSettings(BaseModel):
    model_name: str = 'sentence-transformers/all-MiniLM-L6-v2'
    device: str | None = None
    normalize: bool = False
    local_files_only: bool = False
    batch_size: int = Field(default=32, ge=1)


class EmbeddingSettings(BaseModel):
    backend: Literal['api', 'local'] = 'api'
    api: EmbeddingAPISettings = Field(default_factory=EmbeddingAPISettings)
    local: EmbeddingLocalSettings = Field(default_factory=EmbeddingLocalSettings)


class LightRAGSettings(BaseModel):
    endpoint: str = 'http://127.0.0.1:9621'
    base_url: str = 'http://127.0.0.1:9621'
    embedding_model: Literal['openai', 'local'] = 'openai'
    working_dir: str = './data/lightrag_store'
    query_path: str = '/query'
    upsert_path: str = '/documents/texts'
    delete_path: str = '/documents/delete_document'
    timeout_seconds: float = Field(default=30.0, gt=0)


class ObsidianWriterSettings(BaseModel):
    mode: Literal['fs', 'advanced-uri'] = 'fs'
    vault_name: str | None = None
    advanced_uri_base: str = 'obsidian://advanced-uri'
    filelock_timeout_seconds: float = Field(default=5.0, gt=0)


class OpenAISettings(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    service_name: str = 'openai'
    env_vars: tuple[str, ...] = ('OPENAI_API_KEY', 'HERMES_MEMORY_OPENAI_API_KEY')
    timeout_seconds: float = Field(default=60.0, gt=0)


class AnthropicSettings(BaseModel):
    model: str | None = None
    api_key: str | None = None
    service_name: str = 'anthropic'
    env_vars: tuple[str, ...] = ('ANTHROPIC_API_KEY', 'HERMES_MEMORY_ANTHROPIC_API_KEY')
    timeout_seconds: float = Field(default=60.0, gt=0)


class LLMSettings(BaseModel):
    provider: Literal['openai', 'anthropic'] = 'openai'
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)


class GDriveMCPSettings(BaseModel):
    enabled: bool = False
    server_name: str = 'gdrive'
    timeout_seconds: float = Field(default=30.0, gt=0)


class InboxSettings(BaseModel):
    similarity_top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    merge_queue_filename: str = '.hermes-inbox-merge-queue.jsonl'


class MCPSettings(BaseModel):
    server_name: str = 'hermes-memory-provider'
    server_version: str = '0.14.0'
    instructions: str = (
        'Hermes memory provider MCP server. '
        'Exposes search, sync, inbox submit, and status tools over stdio.'
    )
    transport: Literal['stdio'] = 'stdio'


class SyncConfig(BaseModel):
    scheduler: Literal['internal', 'cron'] = 'internal'
    interval_minutes: int = Field(default=30, ge=1)
    on_startup: bool = True
    cron_expression: str = '*/30 * * * *'

    @field_validator('cron_expression', mode='before')
    @classmethod
    def normalize_cron_expression(cls, value: object) -> object:
        if value is None:
            return '*/30 * * * *'
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError('cron_expression must not be empty')
        if len(normalized.split()) != 5:
            raise ValueError('cron_expression must contain exactly 5 fields')
        return normalized


class HermesMemorySettings(BaseSettings):
    """Runtime settings injected into core utilities and backends."""

    model_config = SettingsConfigDict(
        env_prefix='HERMES_MEMORY_',
        env_nested_delimiter='__',
        extra='ignore',
    )

    resource_package: str = 'plugins.memory.hermes_memory.config.resources'
    resource_system_root: str = '_system'
    vault_root: Path | None = None
    skills_root: Path = Path('~/.hermes/skills')
    quarantine_dirname: str = '_quarantine'
    timezone: str = 'UTC'
    log_level: str = 'INFO'
    wikilink_max_links: int = Field(default=2, ge=1, le=10)
    wikilink_top_k: int = Field(default=8, ge=1, le=50)
    wikilink_score_threshold: float = Field(default=0.0, ge=0.0)
    openclaw_config_path: Path = Path('~/.openclaw/openclaw.json')
    custom_types: tuple[str, ...] = ()
    notion: NotionSettings = Field(default_factory=NotionSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    lightrag: LightRAGSettings = Field(default_factory=LightRAGSettings)
    obsidian_writer: ObsidianWriterSettings = Field(default_factory=ObsidianWriterSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    gdrive_mcp: GDriveMCPSettings = Field(default_factory=GDriveMCPSettings)
    inbox: InboxSettings = Field(default_factory=InboxSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    @field_validator('custom_types', mode='before')
    @classmethod
    def normalize_custom_types(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            return value
        normalized: list[str] = []
        seen: set[str] = set(BUILTIN_NOTE_TYPES)
        for raw_item in values:
            item = str(raw_item).strip().lower()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return tuple(normalized)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings, file_secret_settings]
        yaml_source = _yaml_settings_source(settings_cls)
        if yaml_source is not None:
            sources.append(yaml_source)
        return tuple(sources)


def _yaml_settings_source(settings_cls: type[BaseSettings]) -> PydanticBaseSettingsSource | None:
    configured = os.getenv('HERMES_MEMORY_CONFIG_FILE')
    if configured:
        yaml_path = Path(configured)
    else:
        yaml_path = _DEFAULT_CONFIG_PATH
    if not yaml_path.exists():
        return None
    return YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path)
