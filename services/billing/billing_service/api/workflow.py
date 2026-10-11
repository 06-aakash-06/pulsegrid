"""Service-only Billing metadata leaf. No owner recursion or money mutation."""
import base64
import json
from datetime import datetime,timezone
from fastapi import APIRouter,Request,Depends,Query,HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select,text
from .. import models as m
from ..schemas import ID
from ..authorization import bearer
from ..database import get_database_session
from ..ledger import append_audit

router=APIRouter()


@router.get('/internal/v1/appointments/{appointment_id}/workflow-snapshot')
async def snapshot(request:Request,appointment_id:ID,patient_id:ID,cursor:str|None=Query(None,max_length=2048),
                   limit:int=Query(100,ge=1,le=100),session=Depends(get_database_session)):
    if set(request.query_params)-{'patient_id','cursor','limit'} or any(len(request.query_params.getlist(k))!=1 for k in request.query_params):
        raise HTTPException(422)
    if request.app.state.auth_verifier.service(bearer(request),'workflow:billing-read')!='appointment':
        raise HTTPException(403)
    async with session.begin():
        invoice=(await session.execute(select(m.invoices).where(m.invoices.c.appointment_id==int(appointment_id)))).mappings().first()
        if invoice and str(invoice['patient_id'])!=patient_id:raise HTTPException(404)
        episode=(await session.execute(text('SELECT patient_id,revision FROM billing_episode_revisions WHERE appointment_id=:id'),{'id':int(appointment_id)})).mappings().first()
        if episode and str(episode['patient_id'])!=patient_id:raise HTTPException(404)
        revision=episode['revision'] if episode else 1;offset=0
        if cursor:
            try:
                data=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if data['a']!=appointment_id or data['p']!=patient_id or type(data['o']) is not int or data['o']<0:raise ValueError()
                if data['r']!=revision:raise HTTPException(409,detail='source_changed')
                offset=data['o']
            except (ValueError,KeyError,TypeError):raise HTTPException(422) from None
        value=None;next_cursor=None
        if invoice:
            keys=(await session.execute(select(m.invoice_items.c.source_service,m.invoice_items.c.source_item_id)
                .where(m.invoice_items.c.invoice_id==invoice['id']).order_by(m.invoice_items.c.id)
                .offset(offset).limit(limit+1))).mappings().all()
            value=dict(id=str(invoice['id']),status=invoice['status'],currency=invoice['currency'],
                total_minor=invoice['total_minor'],paid_minor=invoice['paid_minor'],
                balance_minor=invoice['total_minor']-invoice['paid_minor'],version=invoice['version'],
                charge_source_keys=[dict(source_service=k['source_service'],source_item_id=str(k['source_item_id'])) for k in keys[:limit]])
            if len(keys)>limit:next_cursor=base64.urlsafe_b64encode(json.dumps(dict(a=appointment_id,p=patient_id,r=revision,o=offset+limit)).encode()).decode().rstrip('=')
        latest=(await session.execute(text('SELECT revision FROM billing_episode_revisions WHERE appointment_id=:id'),{'id':int(appointment_id)})).scalar_one_or_none() or 1
        if latest!=revision:raise HTTPException(409,detail='source_changed')
        await append_audit(session,request,action='invoice.workflow_snapshot_read',actor_user_id='0',resource_id=int(appointment_id))
    return JSONResponse(dict(snapshot=dict(appointment_id=appointment_id,patient_id=patient_id,revision=revision,
        invoice=value,observed_at=datetime.now(timezone.utc).isoformat()),next_cursor=next_cursor),
        headers={'ETag':f'"{revision}"','Cache-Control':'no-store'})
