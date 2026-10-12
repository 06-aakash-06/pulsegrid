"""Appointment-owned navigation aliases; registration is coordinator-controlled."""

from .registration import register_routes, register_tables, revoke_for_booking_change
from .schema_spec import schema_spec

__all__ = [
    "register_routes",
    "register_tables",
    "revoke_for_booking_change",
    "schema_spec",
]
