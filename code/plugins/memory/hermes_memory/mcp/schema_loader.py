from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_SCHEMA_ROOT = Path(__file__).resolve().parent / 'schemas'



def load_schema(filename: str) -> dict[str, Any]:
    path = _SCHEMA_ROOT / filename
    loaded: object = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(loaded, dict):
        raise ValueError(f'MCP schema must deserialize to an object: {filename}')
    return loaded
