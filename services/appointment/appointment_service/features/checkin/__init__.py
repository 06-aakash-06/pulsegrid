"""Secure, appointment-scoped check-in links and redemption."""

from .registration import register_routes, register_tables, revoke_for_booking_change, schema_spec

__all__ = [
    "register_routes",
    "register_tables",
    "revoke_for_booking_change",
    "schema_spec",
]
