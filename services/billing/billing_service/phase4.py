"""Billing-only crawler composition and versioned, idempotent estimate commands."""
import asyncio,json,os
from contextvars import ContextVar
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select,text
from fastapi import HTTPException
from . import models as m
from .authorization import authenticated_user,verify_current_role
from .api.billing import BillingActor,assert_invoice_scope,precondition_error,send_outcome
from .idempotency import validated_key,request_fingerprint,lock_and_read,save_outcome,StoredOutcome
from .ledger import append_outbox,new_id
from .features.insurance import register_routes,SQLAlchemyInsuranceRepository,AllowlistedFetcher,SourceConfig,worker_tick

_context=ContextVar('insurance_request',default=None)

def enabled():
    value=os.environ.get('PULSEGRID_BILLING_PHASE4_INSURANCE_ENABLED','false')
    if value not in ('true','false'): raise ValueError('Invalid insurance flag')
    return value=='true'

class Ports:
    observer=None
    owner='billing'
    enabled=True
    now=staticmethod(lambda:datetime.now(timezone.utc))
    def __init__(self,app):
        self.app=app
        self.observer=app.state.phase4_observer
        self.repository=SQLAlchemyInsuranceRepository(self.read_session,self.allocate_id,audit_outbox=self.audit_outbox)
    def read_session(self): return self.app.state.database.session_factory()
    async def allocate_id(self):
        from pulsegrid_unique_id import IdUnavailable
        try:return await self.app.state.phase4_ids.next_id()
        except IdUnavailable as error:
            self.observer.increment("pulsegrid_id_failure_total",{"outcome":str(error)})
            raise HTTPException(503,detail={'code':'dependency_unavailable'}) from None
    async def authorize(self,request,roles,resource_id,write):
        principal=await authenticated_user(request)
        role=next((r for r in roles if r in principal.roles),None)
        if role is None:raise HTTPException(403)
        await verify_current_role(request,principal,role)
        if '/invoices/' in request.url.path:
            async with self.read_session() as session:
                row=(await session.execute(select(m.invoices).where(m.invoices.c.id==int(resource_id)))).mappings().first()
                if row is None:raise HTTPException(404)
                assert_invoice_scope(row,BillingActor(principal,role))
        return principal
    async def command(self,request,principal,route_key,body,if_match,operation):
        # Resource path participates in both dedup identity and fingerprint.
        key=validated_key(request)
        route=request.url.path
        fingerprint=request_fingerprint(body,resource_ids={'path':route},if_match=if_match)
        token=_context.set((request,principal))
        try:
            async with self.read_session() as session,session.begin():
                previous=await lock_and_read(session,principal,route,key,fingerprint)
                if previous is not None:return send_outcome(previous)
                if '/invoices/' in route:
                    resource=int(request.path_params['invoice_id']);table=m.invoices
                else:
                    resource=int(request.path_params['provider_id']);table=m.insurance_providers
                row=(await session.execute(select(table).where(table.c.id==resource).with_for_update())).mappings().first()
                if row is None:raise HTTPException(404)
                if table is m.invoices:
                    role='billing_staff' if 'billing_staff' in principal.roles else 'patient'
                    assert_invoice_scope(row,BillingActor(principal,role))
                error=precondition_error(request,if_match,row['version'])
                if error is not None:return send_outcome(error)
                status,result,version=await operation(session,None)
                outcome=StoredOutcome(status,result,f'"{version}"')
                await save_outcome(session,principal,route,key,fingerprint,outcome)
            return send_outcome(outcome)
        finally:_context.reset(token)
    async def read_invoice(self,session,invoice_id):
        row=(await session.execute(select(m.invoices).where(m.invoices.c.id==int(invoice_id)))).mappings().first()
        if row is None:return None
        rows=(await session.execute(select(m.tariffs.c.charge_code,(m.invoice_items.c.quantity*m.invoice_items.c.unit_amount_minor).label('amount_minor')).join(m.invoice_items,m.invoice_items.c.tariff_id==m.tariffs.c.id).where(m.invoice_items.c.invoice_id==int(invoice_id)))).mappings().all()
        return {'id':str(row['id']),'version':row['version'],'balance_minor':row['total_minor']-row['paid_minor'],'items':[dict(r) for r in rows]}
    async def read_provider(self,session,provider_id):
        row=(await session.execute(select(m.insurance_providers).where(m.insurance_providers.c.id==int(provider_id)))).mappings().first()
        return dict(row) if row else None
    async def claim_runs(self,session,now,limit):return await self.repository.claim_runs(session,now,limit)
    async def audit_outbox(self,session,*,action,aggregate_type,aggregate_id,aggregate_version,payload):
        if action=='insurance.estimate_created':
            aggregate_type='insurance_estimate';aggregate_id=int(payload['estimate_id']);aggregate_version=1
        context=_context.get()
        request,principal=context if context else (SimpleNamespace(state=SimpleNamespace(request_id=uuid4(),correlation_id=uuid4(),traceparent=None)),None)
        metadata={'action':action,'result':'success','resource_id':str(aggregate_id),'request_id':str(request.state.request_id),'correlation_id':str(request.state.correlation_id),'occurred_at':self.now().isoformat().replace('+00:00','Z')}
        metadata.update({'actor_user_id':principal.user_id} if principal else {'actor_service':'billing'})
        await session.execute(text('SELECT public.billing_append_insurance_audit(:id,CAST(:metadata AS jsonb))'),{'id':new_id(),'metadata':json.dumps(metadata)})
        await append_outbox(session,request,event_type='billing.'+action+'.v1',aggregate_type=aggregate_type,aggregate_id=aggregate_id,aggregate_version=aggregate_version,payload=payload)


def mount(app):
    if enabled():
        app.state.insurance_ports=Ports(app)
        register_routes(app,app.state.insurance_ports)

async def start(app):
    if not enabled():return
    from pulsegrid_unique_id import Config,Generator,PostgresWorkerStore,worker_identity
    replica=int(os.environ['PULSEGRID_BILLING_PHASE4_REPLICA_CODE'])
    worker=int(os.environ['PULSEGRID_BILLING_PHASE4_WORKER_ID'])
    if worker!=worker_identity(5,replica):raise ValueError('Invalid Billing deployment worker allocation')
    dsn=app.state.settings.database_url.render_as_string(hide_password=False).replace('postgresql+psycopg://','postgresql://')
    app.state.phase4_ids=Generator(Config(worker),PostgresWorkerStore(dsn),observer=app.state.phase4_observer);await app.state.phase4_ids.start()
    config=json.loads(Path(os.environ['PULSEGRID_BILLING_PHASE4_SOURCES_FILE']).read_text())
    sources=[SourceConfig(str(x['provider_id']),x['source_id'],x['base_url'],frozenset(x['allowed_ips'])) for x in config]
    ports=app.state.insurance_ports
    ports.fetcher=AllowlistedFetcher(sources)
    async def loop():
        while True:
            try:await worker_tick(ports)
            except asyncio.CancelledError:raise
            except Exception:app.state.logger.error('insurance_worker_failed')
            await asyncio.sleep(5)
    app.state.insurance_task=asyncio.create_task(loop())

async def close(app):
    if hasattr(app.state,'insurance_task'):
        app.state.insurance_task.cancel();await asyncio.gather(app.state.insurance_task,return_exceptions=True)
        await app.state.insurance_ports.fetcher.aclose()
    if hasattr(app.state,'phase4_ids'):await app.state.phase4_ids.close()
