import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from appointment_service import operations as op
from appointment_service.dependencies import DomainClient
from appointment_service.features.waitlist.eligibility import fetch


@pytest.mark.parametrize('mode',['valid','missing','duplicate','active_missing','oversize','outage'])
def test_batch_leaf_service_only_bounded_and_strict(mode):
    calls=[]
    def transport(request):
        calls.append(request)
        assert request.method=='POST'
        assert request.url.path=='/internal/v1/patients/waitlist-eligibility'
        assert 'X-Delegated-Authorization' not in request.headers
        body=dict(items=[dict(patient_id='12',active=True,version=1)],observed_at=op.wire_time(op.now()))
        if mode=='missing':
            body['items'][0]['patient_id']='13'
        elif mode=='duplicate':
            body['items']*=2
        elif mode=='active_missing':
            body['items'][0]['version']=0
        elif mode=='oversize':
            return httpx.Response(200,content=b' ' * 262145)
        elif mode=='outage':
            return httpx.Response(503)
        return httpx.Response(200,json=body)
    req=SimpleNamespace(state=SimpleNamespace(request_id='synthetic-request',correlation_id='synthetic-correlation'),
        app=SimpleNamespace(state=SimpleNamespace(auth_config=None,domain_client=DomainClient(httpx.MockTransport(transport)))))
    with patch('appointment_service.features.waitlist.eligibility.service_token',return_value='synthetic-test-only'):
        if mode=='valid':
            value=asyncio.run(fetch(req,['12']))
            assert value.items[0].patient_id=='12'
        else:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(fetch(req,['12']))
            assert exc.value.status_code==503
    assert 1<=len(calls)<=2


def test_half_open_single_probe_and_timeout_status():
    import time
    async def run():
        calls=[]
        async def transport(request):
            calls.append(request)
            await asyncio.sleep(.01)
            return httpx.Response(200,json=dict(items=[dict(patient_id='12',active=True,version=1)],observed_at=op.wire_time(op.now())))
        state=DomainClient(httpx.MockTransport(transport));state.open_until['patient']=time.monotonic()-1
        state.failures['patient']=5
        request=SimpleNamespace(state=SimpleNamespace(request_id='test',correlation_id='test'),
            app=SimpleNamespace(state=SimpleNamespace(auth_config=None,domain_client=state)))
        results=await asyncio.gather(fetch(request,['12']),fetch(request,['12']),return_exceptions=True)
        assert sum(isinstance(r,EligibilityBatch) for r in results)==1
        assert sum(isinstance(r,HTTPException) and r.status_code==503 for r in results)==1
        assert len(calls)==1
        async def timeout(request):
            raise httpx.ReadTimeout('synthetic')
        state.transport=httpx.MockTransport(timeout)
        with pytest.raises(HTTPException) as exc:
            await fetch(request,['12'])
        assert exc.value.status_code==504
    from appointment_service.features.waitlist.wire import EligibilityBatch
    with patch('appointment_service.features.waitlist.eligibility.service_token',return_value='synthetic-test-only'):
        asyncio.run(run())
