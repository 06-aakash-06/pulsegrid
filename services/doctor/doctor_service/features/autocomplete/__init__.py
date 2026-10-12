"""Unmounted Doctor-owned autocomplete adapter exports."""

from .routes import create_router, health, register_routes, refresh_index, refresh_loop
from .storage import (
    filter_visible,
    load_snapshot,
    prefix_query,
    read_revision,
    register_tables,
    schema_spec,
)

__all__ = [
    "create_router",
    "filter_visible",
    "health",
    "load_snapshot",
    "prefix_query",
    "read_revision",
    "register_tables",
    "refresh_index",
    "refresh_loop",
    "register_routes",
    "schema_spec",
]
