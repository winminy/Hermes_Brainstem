from __future__ import annotations

import json
import logging
from typing import Any

try:
    import structlog as _structlog
except ModuleNotFoundError:  # pragma: no cover - exercised via reload test
    structlog: Any | None = None
else:
    structlog = _structlog

from plugins.memory.hermes_memory.config.settings import HermesMemorySettings


class _StdlibBoundLogger:
    def __init__(self, logger: logging.Logger, context: dict[str, Any] | None = None) -> None:
        self._logger = logger
        self._context = dict(context or {})

    def bind(self, **kwargs: Any) -> "_StdlibBoundLogger":
        merged = dict(self._context)
        merged.update(kwargs)
        return type(self)(self._logger, merged)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._log(logging.INFO, event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, event, exc_info=True, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, event, **kwargs)

    def _log(self, level: int, event: str, *, exc_info: bool = False, **kwargs: Any) -> None:
        payload = dict(self._context)
        payload.update(kwargs)
        message = event
        if payload:
            message = f'{event} {json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}'
        self._logger.log(level, message, exc_info=exc_info)


def configure_logging(settings: HermesMemorySettings | None = None) -> Any:
    resolved = settings or HermesMemorySettings()
    level_name = resolved.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format='%(message)s')
    if structlog is None:
        return _StdlibBoundLogger(logging.getLogger('hermes_memory'))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt='iso', utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger('hermes_memory')
