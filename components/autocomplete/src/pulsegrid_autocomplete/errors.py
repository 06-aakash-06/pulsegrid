"""Typed failures shared by the pure autocomplete component."""

from __future__ import annotations


class AutocompleteInputError(ValueError):
    """A prefix, limit, kind, or suggestion is outside the frozen contract."""


class IndexTooLarge(RuntimeError):
    """An index exceeded a configured entry or estimated-memory limit."""

    def __init__(
        self,
        reason: str,
        *,
        entries: int,
        nodes: int,
        estimated_bytes: int,
    ) -> None:
        self.reason = reason
        self.entries = entries
        self.nodes = nodes
        self.estimated_bytes = estimated_bytes
        super().__init__(reason)
