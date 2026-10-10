"""Service-scoped environment configuration; credentials are never logged."""

from __future__ import annotations
import math
import logging
import os
from dataclasses import dataclass, field
from typing import Mapping
from sqlalchemy import URL
from .constants import SERVICE_NAME


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"
    db_host: str = ""
    db_port: int = 5432
    db_name: str = ""
    db_user: str = ""
    db_password: str = field(default="", repr=False)
    db_pool_size: int = 3
    db_max_overflow: int = 2
    db_pool_timeout: float = 2.0
    db_connect_timeout: int = 2
    db_statement_timeout_ms: int = 2000
    db_health_timeout: float = 3.0

    @property
    def database_configured(self) -> bool:
        return all((self.db_host, self.db_name, self.db_user, self.db_password))

    @property
    def database_url(self) -> URL:
        if not self.database_configured:
            raise ValueError("Database configuration is incomplete")
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def connection_options(self) -> dict:
        return {
            "connect_timeout": self.db_connect_timeout,
            "options": f"-c statement_timeout={self.db_statement_timeout_ms} -c lock_timeout=1000 -c timezone=UTC",
        }

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        prefix = f"PULSEGRID_{SERVICE_NAME.upper()}_"
        defaults = cls()
        kwargs = {}
        for name in cls.__dataclass_fields__:
            value = values.get(prefix + name.upper())
            if value is None:
                continue
            default = getattr(defaults, name)
            try:
                kwargs[name] = (
                    type(default)(value)
                    if isinstance(default, (int, float))
                    else value.strip() if name != "db_password" else value
                )
            except ValueError:
                raise ValueError(
                    f"{prefix}{name.upper()} has an invalid numeric value"
                ) from None
        settings = cls(**kwargs)
        if not settings.environment:
            raise ValueError(f"{prefix}ENVIRONMENT must not be empty")
        level = settings.log_level.upper()
        if not isinstance(getattr(logging, level, None), int):
            raise ValueError(f"{prefix}LOG_LEVEL must be a standard logging level")
        object.__setattr__(settings, "log_level", level)
        db_parts = (
            settings.db_host,
            settings.db_name,
            settings.db_user,
            settings.db_password,
        )
        if any(db_parts) and not all(db_parts):
            raise ValueError(
                f"{prefix}DB_HOST/DB_NAME/DB_USER/DB_PASSWORD must be configured together"
            )
        for name in (
            "db_port",
            "db_pool_size",
            "db_pool_timeout",
            "db_connect_timeout",
            "db_statement_timeout_ms",
            "db_health_timeout",
        ):
            if (
                not math.isfinite(getattr(settings, name))
                or getattr(settings, name) <= 0
            ):
                raise ValueError(f"{prefix}{name.upper()} must be positive")
        if not 1 <= settings.db_port <= 65535 or settings.db_max_overflow < 0:
            raise ValueError("Invalid database port or overflow limit")
        return settings
