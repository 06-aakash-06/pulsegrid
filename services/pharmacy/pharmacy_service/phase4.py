"""Owner composition of the independent trie; no foreign storage or authority."""
import asyncio
import os
from contextlib import asynccontextmanager
from pulsegrid_autocomplete import IndexRegistry, IndexLimits
from pulsegrid_autocomplete.lifecycle import refresh_loop
from .authorization import authenticated_user
from .features.autocomplete import storage, routes


def enabled():
    value=os.environ.get('PULSEGRID_PHARMACY_PHASE4_AUTOCOMPLETE_ENABLED','false')
    if value not in ('true','false'): raise ValueError('Invalid Phase 4 feature flag')
    return value=='true'

class Ports:
    owner='pharmacy'
    observer=None
    def __init__(self,app):
        self.app=app
        self.observer=app.state.phase4_observer
        self.index_registry=IndexRegistry()
        entries=int(os.environ.get('PULSEGRID_PHARMACY_PHASE4_AUTOCOMPLETE_MAX_ENTRIES','100000'))
        budget=int(os.environ.get('PULSEGRID_PHARMACY_PHASE4_AUTOCOMPLETE_MAX_BYTES',str(64*1024*1024)))
        if entries>100000 or budget>64*1024*1024:raise ValueError('Unreviewed index budget increase')
        self.index_limits=IndexLimits(entries,budget)
    async def authorize(self,request,roles,resource_id,write):
        return await authenticated_user(request)
    @asynccontextmanager
    async def read_session(self):
        from sqlalchemy import text
        from fastapi import HTTPException
        factory=self.app.state.database.session_factory
        if factory is None: raise HTTPException(503)
        async with factory() as session,session.begin():
            await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            yield session
    read_revision=staticmethod(storage.read_revision)
    load_snapshot=staticmethod(storage.load_snapshot)
    prefix_query=staticmethod(storage.prefix_query)
    filter_visible=staticmethod(storage.filter_visible)


def mount(app):
    if enabled():
        app.state.autocomplete_ports=Ports(app)
        routes.register_routes(app,app.state.autocomplete_ports)

async def start(app):
    if hasattr(app.state,'autocomplete_ports'):
        app.state.autocomplete_stop=asyncio.Event()
        app.state.autocomplete_task=asyncio.create_task(refresh_loop(app.state.autocomplete_ports,app.state.autocomplete_stop))

async def close(app):
    if hasattr(app.state,'autocomplete_task'):
        app.state.autocomplete_stop.set()
        app.state.autocomplete_task.cancel()
        await asyncio.gather(app.state.autocomplete_task,return_exceptions=True)
