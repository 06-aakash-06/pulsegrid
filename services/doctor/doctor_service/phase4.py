"""Owner composition of the independent trie; no foreign storage or authority."""
import asyncio
import os
from contextlib import asynccontextmanager
from pulsegrid_autocomplete import IndexRegistry, IndexLimits
from pulsegrid_autocomplete.lifecycle import refresh_loop
from .authorization import authenticated_user
from .features.autocomplete import storage, routes


def enabled():
    value=os.environ.get('PULSEGRID_DOCTOR_PHASE4_AUTOCOMPLETE_ENABLED','false')
    if value not in ('true','false'): raise ValueError('Invalid Phase 4 feature flag')
    return value=='true'

class Ports:
    owner='doctor'
    observer=None
    def __init__(self,app):
        self.app=app
        self.observer=app.state.phase4_observer
        self.index_registry=IndexRegistry()
        entries=int(os.environ.get('PULSEGRID_DOCTOR_PHASE4_AUTOCOMPLETE_MAX_ENTRIES','100000'))
        budget=int(os.environ.get('PULSEGRID_DOCTOR_PHASE4_AUTOCOMPLETE_MAX_BYTES',str(64*1024*1024)))
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
    mount_cache(app)
    if enabled():
        app.state.autocomplete_ports=Ports(app)
        routes.register_routes(app,app.state.autocomplete_ports)

async def start(app):
    if hasattr(app.state,'autocomplete_ports'):
        app.state.autocomplete_stop=asyncio.Event()
        app.state.autocomplete_task=asyncio.create_task(refresh_loop(app.state.autocomplete_ports,app.state.autocomplete_stop))

async def close(app):
    if hasattr(app.state,'directory_cache'): await app.state.directory_cache.close()
    if hasattr(app.state,'autocomplete_task'):
        app.state.autocomplete_stop.set()
        app.state.autocomplete_task.cancel()
        await asyncio.gather(app.state.autocomplete_task,return_exceptions=True)


def mount_cache(app):
    import json
    from pathlib import Path
    from pulsegrid_consistent_hashing import HashRing, RingSnapshot
    from pulsegrid_key_value_cache import Cache, redis_client
    value=os.environ.get('PULSEGRID_DOCTOR_PHASE4_CACHE_ENABLED','false')
    if value not in ('true','false'): raise ValueError('Invalid cache flag')
    if value=='true':
        config=json.loads(Path(os.environ['PULSEGRID_DOCTOR_PHASE4_CACHE_CONFIG_FILE']).read_text())
        ring=HashRing(RingSnapshot(config['epoch'],128,tuple(config['nodes'])))
        app.state.directory_cache=Cache(ring,{node:redis_client(url) for node,url in config['nodes'].items()},observer=app.state.phase4_observer)

async def directory_page(app, principal, filters):
    from sqlalchemy import text
    from .features.directory_cache import cache_projection, load_projection, read_revision
    from .repository import get_doctors_by_ids, doctor_profile, list_doctors
    factory=app.state.database.session_factory
    async with factory() as session:
        revision=await read_revision(session)
    async def loader():
        async with factory() as session:
            return await load_projection(session,filters)
    projection=await cache_projection(app.state.directory_cache,revision,filters,loader)
    async with factory() as session,session.begin():
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        current=await read_revision(session)
        if current==revision:
            rows=await get_doctors_by_ids(session,[item['id'] for item in projection['items']])
            if all(row and row['active'] for row in rows):
                return {'items':[doctor_profile(row) for row in rows],'next_cursor':projection['next_cursor']}
        rows=await list_doctors(session,active=True,specialty_id=filters.specialty_id,query=filters.query,cursor=filters.cursor,limit=filters.limit+1)
        from .api.doctors import _page_cursor
        from .wire import filter_digest
        digest=filter_digest({'active':True,'q':filters.query,'specialty_id':filters.specialty_id})
        return {'items':[doctor_profile(row) for row in rows[:filters.limit]],'next_cursor':_page_cursor(rows,filters.limit,digest)}
