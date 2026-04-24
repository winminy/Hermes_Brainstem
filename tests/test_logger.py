from __future__ import annotations

import builtins
import importlib
import logging
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

from _pytest.logging import LogCaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from plugins.memory.hermes_memory.config import HermesMemorySettings


_LOGGER_MODULE = 'plugins.memory.hermes_memory.core.logger'


def _import_logger_module() -> ModuleType:
    sys.modules.pop(_LOGGER_MODULE, None)
    return importlib.import_module(_LOGGER_MODULE)


def test_configure_logging_returns_bound_logger_without_structlog(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == 'structlog':
            raise ModuleNotFoundError("No module named 'structlog'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, 'structlog', raising=False)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    logger_module = _import_logger_module()
    logger = logger_module.configure_logging(HermesMemorySettings(log_level='DEBUG')).bind(component='fallback')

    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError('boom')
        except RuntimeError:
            logger.exception('logger.fallback_test', item='value')

    assert hasattr(logger, 'bind')
    assert caplog.records
    assert caplog.records[-1].exc_info is not None
    assert 'logger.fallback_test' in caplog.records[-1].message
    assert '"component": "fallback"' in caplog.records[-1].message
    assert '"item": "value"' in caplog.records[-1].message


def test_configure_logging_uses_structlog_when_available(monkeypatch: MonkeyPatch) -> None:
    fake_logger = object()

    class FakeStructlog(ModuleType):
        def __init__(self) -> None:
            super().__init__('structlog')
            self.contextvars = SimpleNamespace(merge_contextvars='merge_contextvars')
            self.stdlib = SimpleNamespace(add_log_level='add_log_level', LoggerFactory=lambda: 'logger_factory')
            self.processors = SimpleNamespace(
                TimeStamper=lambda **kwargs: ('timestamp', kwargs),
                JSONRenderer=lambda: 'json_renderer',
            )
            self.config_calls: list[dict[str, object]] = []

        def configure(self, **kwargs: object) -> None:
            self.config_calls.append(kwargs)

        def make_filtering_bound_logger(self, level: int) -> tuple[str, int]:
            return ('wrapper', level)

        def get_logger(self, name: str) -> object:
            assert name == 'hermes_memory'
            return fake_logger

    fake_structlog = FakeStructlog()
    monkeypatch.setitem(sys.modules, 'structlog', fake_structlog)
    logger_module = _import_logger_module()

    logger = logger_module.configure_logging(HermesMemorySettings(log_level='WARNING'))

    assert logger is fake_logger
    assert fake_structlog.config_calls
    config_call = fake_structlog.config_calls[-1]
    assert config_call['wrapper_class'] == ('wrapper', logging.WARNING)
    assert config_call['logger_factory'] == 'logger_factory'
