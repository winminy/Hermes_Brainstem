from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from .frontmatter import MarkdownDocument


class InvariantViolationError(ValueError):
    """Raised when an immutable frontmatter field changes."""


@dataclass(frozen=True, slots=True)
class InvariantGuard:
    immutable_fields: tuple[str, ...] = ('uuid', 'date', 'source')

    def assert_preserved(self, existing: MarkdownDocument, candidate: MarkdownDocument) -> None:
        current = existing.frontmatter
        proposed = candidate.frontmatter
        for field_name in self.immutable_fields:
            if getattr(current, field_name) != getattr(proposed, field_name):
                raise InvariantViolationError(f'invariant field changed: {field_name}')


T = TypeVar('T')


class GuardedWriter(Generic[T]):
    def __init__(self, writer: Callable[[MarkdownDocument], T], guard: InvariantGuard | None = None) -> None:
        self._writer = writer
        self._guard = guard or InvariantGuard()

    def write(self, candidate: MarkdownDocument, *, existing: MarkdownDocument | None = None) -> T:
        if existing is not None:
            self._guard.assert_preserved(existing=existing, candidate=candidate)
        return self._writer(candidate)
