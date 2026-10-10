"""Positive signed BIGINT identifiers generated with the operating-system CSPRNG."""

from secrets import randbelow


def new_id() -> int:
    return randbelow(9223372036854775806) + 1
