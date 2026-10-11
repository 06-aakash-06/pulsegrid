from ... import models as m
from .schema_spec import schema_spec
from .operations import on_slot_released


def register_tables(metadata):
    if metadata is not m.metadata:
        raise ValueError('Appointment metadata required')
    # Dormant objects are reused. promotion_jobs is added by G2 aggregate metadata.
    for table in (m.waitlist_entries,m.patient_status_snapshots):
        if metadata.tables[table.name] is not table:
            raise ValueError('Shared table identity changed')


def register_routes(app,core):
    from .router import make_router
    app.include_router(make_router(core))
