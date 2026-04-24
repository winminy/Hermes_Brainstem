from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from mcp import types
from mcp.shared.exceptions import McpError



def raise_invalid_params(message: str, *, data: Mapping[str, Any] | None = None) -> NoReturn:
    raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message=message, data=dict(data) if data is not None else None))



def raise_internal_error(message: str, *, data: Mapping[str, Any] | None = None) -> NoReturn:
    raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message=message, data=dict(data) if data is not None else None))



def raise_method_not_found(message: str, *, data: Mapping[str, Any] | None = None) -> NoReturn:
    raise McpError(types.ErrorData(code=types.METHOD_NOT_FOUND, message=message, data=dict(data) if data is not None else None))
