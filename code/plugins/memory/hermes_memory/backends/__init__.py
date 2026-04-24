from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from typing import TypeVar


class BackendError(RuntimeError):
    """Base backend error."""


class OptionalDependencyError(BackendError):
    """Raised when an optional backend dependency is unavailable."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    same_mode_attempts: int = 2
    alternate_mode_attempts: int = 2
    delay_seconds: float = 0.0

    @property
    def total_attempts(self) -> int:
        return self.same_mode_attempts + self.alternate_mode_attempts


_T = TypeVar('_T')


def run_with_retry(
    primary: Callable[[], _T],
    *,
    fallback: Callable[[], _T] | None = None,
    policy: RetryPolicy | None = None,
) -> _T:
    resolved_policy = policy or RetryPolicy()
    errors: list[BaseException] = []
    for _ in range(resolved_policy.same_mode_attempts):
        try:
            return primary()
        except Exception as exc:
            errors.append(exc)
            if resolved_policy.delay_seconds > 0:
                sleep(resolved_policy.delay_seconds)
    if fallback is not None:
        for _ in range(resolved_policy.alternate_mode_attempts):
            try:
                return fallback()
            except Exception as exc:
                errors.append(exc)
                if resolved_policy.delay_seconds > 0:
                    sleep(resolved_policy.delay_seconds)
    if errors:
        raise BackendError(f'backend operation failed after {resolved_policy.total_attempts} attempts: {errors[-1]}') from errors[-1]
    raise BackendError('backend operation failed without executing any attempts')


__all__ = ['BackendError', 'OptionalDependencyError', 'RetryPolicy', 'run_with_retry']
