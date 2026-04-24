from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcp import types


@dataclass(frozen=True, slots=True)
class ManagedTool:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any]], dict[str, Any]]

    def definition(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            title=self.title,
            description=self.description,
            inputSchema=self.input_schema,
            outputSchema=self.output_schema,
        )
