"""Service-only bounded Patient batch leaf. G3 supplies keys/scope and lifecycle."""
import asyncio
import time
import random
import httpx
from pydantic import ValidationError
from ...authorization import service_token
from ... import operations as op
from .wire import EligibilityBatch


async def fetch(request,patient_ids):
    state=request.app.state.domain_client
    half_open=bool(state.open_until.get('patient',0)) and state.open_until['patient']<=time.monotonic()
    if half_open:
        if getattr(state,'waitlist_half_open_probe',False):
            op.fail('dependency_unavailable',503)
        state.waitlist_half_open_probe=True
    try:
        return await _fetch(request,patient_ids)
    finally:
        if half_open:
            state.waitlist_half_open_probe=False


async def _fetch(request,patient_ids):
    if not 1 <= len(patient_ids) <= 50 or len(set(patient_ids)) != len(patient_ids):
        raise ValueError('Distinct bounded patient IDs required')
    client_state=request.app.state.domain_client
    if client_state.open_until.get('patient',0)>time.monotonic():
        op.fail('dependency_unavailable',503)
    headers={'Authorization':'Bearer '+service_token(request.app.state.auth_config,
        'patients:waitlist-eligibility','patient'),'X-Request-ID':str(request.state.request_id),
        'X-Correlation-ID':str(request.state.correlation_id)}
    if getattr(request.state,'traceparent',None):
        headers['traceparent']=request.state.traceparent
    deadline=min(time.monotonic()+5,getattr(request.state,'dependency_deadline',time.monotonic()+5))
    for attempt in range(2):
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                op.fail('dependency_timeout',504)
            async with asyncio.timeout(min(1,remaining)),httpx.AsyncClient(timeout=min(1,remaining),
                    trust_env=False,follow_redirects=False,transport=client_state.transport) as client:
                async with client.stream('POST','http://patient:8000/internal/v1/patients/waitlist-eligibility',
                        headers=headers,json={'patient_ids':patient_ids}) as response:
                    if response.status_code!=200:
                        raise httpx.TransportError('Eligibility unavailable')
                    raw=bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw)>262144:
                            op.fail('dependency_unavailable',503)
                    batch=EligibilityBatch.model_validate_json(raw)
                    if {i.patient_id for i in batch.items}!=set(patient_ids):
                        op.fail('dependency_unavailable',503)
            client_state.failures['patient']=0
            client_state.open_until['patient']=0
            return batch
        except (httpx.HTTPError,TimeoutError,ValidationError) as exc:
            client_state.failures['patient']=client_state.failures.get('patient',0)+1
            if client_state.failures['patient']>=5:
                client_state.open_until['patient']=time.monotonic()+15
            if attempt==0 and client_state.open_until.get('patient',0)<=time.monotonic():
                await asyncio.sleep(random.uniform(.05,.15))
            else:
                op.fail('dependency_timeout' if isinstance(exc,(httpx.TimeoutException,TimeoutError))
                    else 'dependency_unavailable',504 if isinstance(exc,(httpx.TimeoutException,TimeoutError)) else 503)
