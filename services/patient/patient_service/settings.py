"""Environment-based settings for the patient service."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

from .constants import SERVICE_NAME


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        prefix = f"PULSEGRID_{SERVICE_NAME.upper()}_"
        environment = values.get(f"{prefix}ENVIRONMENT", "development").strip()
        log_level = values.get(f"{prefix}LOG_LEVEL", "INFO").strip().upper()

        if not environment:
            raise ValueError(f"{prefix}ENVIRONMENT must not be empty")
        if not hasattr(logging, log_level) or not isinstance(getattr(logging, log_level), int):
            raise ValueError(f"{prefix}LOG_LEVEL must be a standard logging level")

        return cls(environment=environment, log_level=log_level)
