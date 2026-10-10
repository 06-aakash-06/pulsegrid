"""Exact remote shapes, fail-closed behavior and bounded retry/circuit policy."""
import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from appointment_service import dependencies as dep
from appointment_service.authorization import Principal
from appointment_service.wire import Identity


def context():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(auth_config=None)),
        state=SimpleNamespace(request_id=uuid4(),correlation_id=uuid4(),traceparent=None,dependency_deadline=time.monotonic()+5))


@pytest.mark.parametrize('mode,expected,attempts',[
    ('missing',422,1),('denied',403,1),('invalid',503,1),('oversized',503,1),
    ('redirect',503,1),('timeout',504,2),('outage',503,2),('success',200,1)])
def test_dependency_contract_and_failures(monkeypatch,mode,expected,attempts):
    monkeypatch.setattr(dep,'service_token',lambda *a:'synthetic-service-token')
    calls=[]
    def transport(request):
        calls.append(request)
        assert request.headers['x-delegated-authorization']=='Bearer synthetic-access-token'
        assert request.url.host=='doctor' and request.headers['x-request-id']
        if mode=='timeout': raise httpx.ReadTimeout('test')
        if mode=='outage': return httpx.Response(503)
        if mode=='missing': return httpx.Response(404)
        if mode=='denied': return httpx.Response(403)
        if mode=='redirect': return httpx.Response(302,headers={'Location':'http://untrusted/'})
        if mode=='oversized': return httpx.Response(200,content=b'x'*262145)
        if mode=='invalid': return httpx.Response(200,json={'doctor_id':'1'})
        return httpx.Response(200,json={'doctor_id':'1','staff_user_id':'101','active':True,'version':1})
    async def run():
        client=dep.DomainClient(httpx.MockTransport(transport))
        p=Principal('11','11',frozenset({'patient'}),1,'synthetic-access-token')
        if expected==200:
            assert (await client.get(context(),p,'doctor','/internal/v1/doctors/1/identity','doctors:identity',Identity)).doctor_id=='1'
        else:
            with pytest.raises(HTTPException) as exc:
                await client.get(context(),p,'doctor','/internal/v1/doctors/1/identity','doctors:identity',Identity)
            assert exc.value.status_code==expected
    asyncio.run(run())
    assert len(calls)==attempts


def test_circuit_opens_after_five_failed_attempts(monkeypatch):
    monkeypatch.setattr(dep,'service_token',lambda *a:'synthetic')
    calls=[]
    def transport(request):
        calls.append(request)
        return httpx.Response(503)
    async def run():
        client=dep.DomainClient(httpx.MockTransport(transport))
        p=Principal('11','11',frozenset({'patient'}),1,'synthetic')
        for _ in range(4):
            with pytest.raises(HTTPException):
                await client.get(context(),p,'doctor','/internal/v1/doctors/1/identity','doctors:identity',Identity)
        assert len(calls)==5
        client.open_until['doctor']=time.monotonic()-1
        with pytest.raises(HTTPException):
            await client.get(context(),p,'doctor','/internal/v1/doctors/1/identity','doctors:identity',Identity)
        assert len(calls)==6
    asyncio.run(run())
