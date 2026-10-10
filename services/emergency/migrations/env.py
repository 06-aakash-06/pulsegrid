"""Migration connection uses this service's migration-owner credentials."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from emergency_service.models import metadata
from emergency_service.settings import Settings

settings = Settings.from_env()
if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args=settings.connection_options,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
