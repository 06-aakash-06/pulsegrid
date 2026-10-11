"""Explicit, disabled-by-default registration. G0 never imports absent features."""
from importlib import import_module
from types import MappingProxyType

FEATURE_MODULES = MappingProxyType({
    name: f'appointment_service.features.{name}.registration'
    for name in ('waitlist', 'checkin', 'queue', 'journey')
})
PARTICIPANTS = {
    'waitlist': ('on_slot_released',),
    'checkin': ('revoke_for_booking_change',),
    'queue': ('allocate_on_checkin', 'complete_from_records'),
    'journey': ('on_booking_created', 'on_booking_changed'),
}


def register_extensions(app, core, *, enabled=()):
    """Coordinator supplies reviewed names at G2/G4, never environment discovery.

    Validate all modules before mounting. Static feature routes mount before the
    legacy /{appointment_id} route. No feature is enabled in the G0 app factory.
    """
    names = tuple(enabled)
    if len(set(names)) != len(names) or set(names) - FEATURE_MODULES.keys():
        raise ValueError('Unknown or duplicate Appointment feature')
    if hasattr(app.state, 'appointment_extensions'):
        raise RuntimeError('Appointment extensions already registered')
    modules = {}
    for name in names:
        module = import_module(FEATURE_MODULES[name])
        for export in ('register_routes', 'register_tables', 'schema_spec', *PARTICIPANTS[name]):
            if not callable(getattr(module, export, None)):
                raise TypeError(f'{name} missing required export {export}')
        modules[name] = module
    tables_before = dict(core.metadata.tables)
    for module in modules.values():
        module.register_tables(core.metadata)
        if any(core.metadata.tables.get(k) is not v for k, v in tables_before.items()):
            raise RuntimeError('Feature replaced shared table metadata')
        if not isinstance(module.schema_spec(), dict):
            raise TypeError('schema_spec must return a dict')
    app.state.appointment_extensions = MappingProxyType(modules)
    for module in modules.values():
        module.register_routes(app, core)
