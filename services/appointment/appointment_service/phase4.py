"""Appointment composition: alias commands use canonical owner transactions."""
import json
import os
from fastapi.responses import JSONResponse
from . import phase3_core as core, operations as op
from .authorization import authenticated_user
from .features.short_links import register_routes, register_tables
from .features.short_links.ports import NoopObserver


def enabled():
    value=os.environ.get('PULSEGRID_APPOINTMENT_PHASE4_SHORT_LINKS_ENABLED','false')
    if value not in ('true','false'): raise ValueError('Invalid short-link flag')
    return value=='true'

class Ports:
    observer=NoopObserver()
    def __init__(self,app):
        self.app=app
        self.observer=app.state.phase4_observer
    async def authorize(self,request,roles,resource_id,write):
        principal=await authenticated_user(request)
        await core.authorize(request,principal,roles,resource_id,write=write)
        return principal
    async def allocate_id(self):
        from pulsegrid_unique_id import IdUnavailable
        try: return await self.app.state.phase4_ids.next_id()
        except IdUnavailable as error:
            self.observer.increment("pulsegrid_id_failure_total",{"outcome":str(error)})
            op.fail('dependency_unavailable',503)
    def read_session(self): return self.app.state.database.session_factory()
    read_workflow=staticmethod(core.read_workflow)
    stage_effect=staticmethod(core.stage_effect)
    async def lock_context(self,session,request,principal,appointment_id):
        from .features.queue.service import _complete_plan
        aid=int(appointment_id)
        booking=await op.row(session,core.m.appointments,aid)
        plan=await _complete_plan(session,booking['doctor_id'],booking['starts_at'].date(),(aid,))
        return await core.lock_context(session,request,core.ActorScope.user(principal),plan)
    async def command(self,request,principal,route_key,body,if_match,operation):
        identity,fingerprint=op.idempotency(request,principal,body)
        async def work(session):
            status,safe_body,version=await operation(session,None)
            return status,safe_body
        status,body=await op.command(self.app.state.database.session_factory,identity,fingerprint,work)
        return JSONResponse(body,status_code=status,headers={'Cache-Control':'no-store','ETag':f'"{body["version"]}"'})
    def token_response(self,response,fields):
        headers={k:v for k,v in response.headers.items() if k.lower()!='content-length'}
        headers['Referrer-Policy']='no-referrer'
        return JSONResponse({**json.loads(response.body),**fields},status_code=response.status_code,headers=headers)


def mount(app):
    if enabled():
        if not app.state.phase3_enabled: raise ValueError('Aliases require Phase 3 workflows')
        register_tables(core.metadata)
        app.state.short_links_enabled=True
        register_routes(app,Ports(app))

async def start(app):
    if enabled():
        from pulsegrid_unique_id import Config, Generator, PostgresWorkerStore, worker_identity
        replica=int(os.environ['PULSEGRID_APPOINTMENT_PHASE4_REPLICA_CODE'])
        worker=int(os.environ['PULSEGRID_APPOINTMENT_PHASE4_WORKER_ID'])
        if worker!=worker_identity(2,replica): raise ValueError('Invalid Appointment deployment worker allocation')
        settings=app.state.settings
        dsn=settings.database_url.render_as_string(hide_password=False).replace('postgresql+psycopg://','postgresql://')
        app.state.phase4_ids=Generator(Config(worker),PostgresWorkerStore(dsn),observer=app.state.phase4_observer)
        await app.state.phase4_ids.start()

async def close(app):
    if hasattr(app.state,'phase4_ids'): await app.state.phase4_ids.close()
