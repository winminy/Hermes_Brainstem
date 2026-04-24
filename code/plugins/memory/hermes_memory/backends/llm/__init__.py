from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from plugins.memory.hermes_memory.config.layer import ConfigLayer

from .. import OptionalDependencyError


@dataclass(frozen=True, slots=True)
class StructuredTool:
    name: str
    description: str
    input_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class StructuredLLMRequest:
    system_prompt: str
    user_prompt: str
    output_schema: Mapping[str, Any]
    tools: tuple[StructuredTool, ...] = field(default_factory=tuple)


class StructuredLLMBackend(Protocol):
    def generate(self, request: StructuredLLMRequest) -> Mapping[str, Any]:
        ...


class OpenAIJSONSchemaLLM:
    def __init__(self, *, config: ConfigLayer, client: object | None = None) -> None:
        self._config = config
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            settings = self._config.settings.llm.openai
            api_key = self._config.resolve_secret(
                yaml_value=settings.api_key,
                service_name=settings.service_name,
                env_vars=settings.env_vars,
            )
            if api_key is None:
                raise RuntimeError('OpenAI API key is not configured. Run hermes-memory-doctor.')
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - optional dependency guard
                raise OptionalDependencyError('openai is not installed. Run hermes-memory-doctor.') from exc
            kwargs: dict[str, Any] = {'api_key': api_key, 'timeout': settings.timeout_seconds}
            if settings.base_url is not None:
                kwargs['base_url'] = settings.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def generate(self, request: StructuredLLMRequest) -> Mapping[str, Any]:
        settings = self._config.settings.llm.openai
        if settings.model is None:
            raise RuntimeError('llm.openai.model must be configured before use')
        response = self.client.responses.create(
            model=settings.model,
            input=[
                {'role': 'system', 'content': request.system_prompt},
                {'role': 'user', 'content': request.user_prompt},
            ],
            text={
                'format': {
                    'type': 'json_schema',
                    'name': 'hermes_structured_output',
                    'schema': dict(request.output_schema),
                    'strict': True,
                }
            },
        )
        output_text = getattr(response, 'output_text', None)
        if isinstance(output_text, str):
            import json

            parsed = json.loads(output_text)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError('OpenAI structured response did not return a JSON object')


class AnthropicToolUseLLM:
    def __init__(self, *, config: ConfigLayer, client: object | None = None) -> None:
        self._config = config
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            settings = self._config.settings.llm.anthropic
            api_key = self._config.resolve_secret(
                yaml_value=settings.api_key,
                service_name=settings.service_name,
                env_vars=settings.env_vars,
            )
            if api_key is None:
                raise RuntimeError('Anthropic API key is not configured. Run hermes-memory-doctor.')
            try:
                from anthropic import Anthropic
            except ImportError as exc:  # pragma: no cover - optional dependency guard
                raise OptionalDependencyError('anthropic is not installed. Run hermes-memory-doctor.') from exc
            self._client = Anthropic(api_key=api_key, timeout=self._config.settings.llm.anthropic.timeout_seconds)
        return self._client

    def generate(self, request: StructuredLLMRequest) -> Mapping[str, Any]:
        settings = self._config.settings.llm.anthropic
        if settings.model is None:
            raise RuntimeError('llm.anthropic.model must be configured before use')
        response = self.client.messages.create(
            model=settings.model,
            system=request.system_prompt,
            max_tokens=4096,
            tools=[
                {
                    'name': tool.name,
                    'description': tool.description,
                    'input_schema': dict(tool.input_schema),
                }
                for tool in request.tools
            ],
            messages=[{'role': 'user', 'content': request.user_prompt}],
        )
        for block in getattr(response, 'content', []):
            if getattr(block, 'type', None) == 'tool_use' and isinstance(getattr(block, 'input', None), dict):
                return cast(Mapping[str, Any], block.input)
        raise ValueError('Anthropic tool_use response did not return a structured object')


def build_structured_llm(config: ConfigLayer, *, client: object | None = None) -> StructuredLLMBackend:
    provider = config.settings.llm.provider
    if provider == 'openai':
        return OpenAIJSONSchemaLLM(config=config, client=client)
    if provider == 'anthropic':
        return AnthropicToolUseLLM(config=config, client=client)
    raise ValueError(f'unsupported llm provider: {provider}')


__all__ = [
    'AnthropicToolUseLLM',
    'OpenAIJSONSchemaLLM',
    'StructuredLLMBackend',
    'StructuredLLMRequest',
    'StructuredTool',
    'build_structured_llm',
]
