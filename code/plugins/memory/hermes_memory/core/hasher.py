from __future__ import annotations

import hashlib


def sha256_hexdigest(payload: str | bytes) -> str:
    data = payload.encode('utf-8') if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()
