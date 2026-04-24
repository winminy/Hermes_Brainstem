from __future__ import annotations

import hashlib

from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest


def test_sha256_hexdigest_is_stable() -> None:
    expected = hashlib.sha256(b'hermes').hexdigest()
    assert sha256_hexdigest('hermes') == expected
