from __future__ import annotations

from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest


def test_sha256_hexdigest_is_stable() -> None:
    assert sha256_hexdigest('hermes') == '8cfde6efdfc4ed5ab1f6acbbd1ba49bf31932f84d0a4c090eb41c7d151e8b180'
