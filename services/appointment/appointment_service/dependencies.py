"""Bounded owner API adapter. No database access or production fixture fallback."""
import asyncio
import random
import time
import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from .authorization import bearer, require_current_role, service_token


class DomainClient:
    def __init__(self, transport=None):
        self.transport=transport
        self.failures={}
        self.open_until={}

    async def get(self, request, principal, owner, path, scope, schema):
        deadline=getattr(request.state,'dependency_deadline',time.monotonic()+5)
        if self.open_until.get(owner,0)>time.monotonic():
            raise HTTPException(503)
        headers={
            'Authorization':'Bearer '+service_token(request.app.state.auth_config,scope,owner),
            'X-Delegated-Authorization':'Bearer '+principal.access_token,
            'X-Request-ID':str(request.state.request_id),
            'X-Correlation-ID':str(request.state.correlation_id),
        }
        if getattr(request.state,'traceparent',None):
            headers['traceparent']=request.state.traceparent
        for attempt in range(2):
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise HTTPException(504)
            failure=503
            try:
                async with asyncio.timeout(min(1,remaining)):
                    async with httpx.AsyncClient(timeout=min(1,remaining),trust_env=False,
                            follow_redirects=False,transport=self.transport) as client:
                        async with client.stream('GET',f'http://{owner}:8000'+path,headers=headers) as result:
                            if result.status_code<500 and result.status_code!=200:
                                if result.status_code==404:
                                    raise HTTPException(422,detail='invalid_reference')
                                raise HTTPException(result.status_code if result.status_code in (401,403,422) else 503)
                            if result.status_code>=500:
                                raise httpx.TransportError('Dependency unavailable')
                            raw=bytearray()
                            async for part in result.aiter_bytes():
                                raw.extend(part)
                                if len(raw)>262144:
                                    raise HTTPException(503)
                            try:
                                value=schema.model_validate_json(raw)
                            except (ValidationError,ValueError):
                                raise HTTPException(503) from None
                self.failures[owner]=0
                self.open_until[owner]=0
                return value
            except (httpx.TimeoutException,TimeoutError):
                failure=504
            except httpx.HTTPError:
                pass
            self.failures[owner]=self.failures.get(owner,0)+1
            if self.failures[owner]>=5:
                self.open_until[owner]=time.monotonic()+15
            if attempt==0 and self.open_until.get(owner,0)<=time.monotonic():
                await asyncio.sleep(random.uniform(.05,.15))
            else:
                raise HTTPException(failure)
        raise HTTPException(failure)


async def current(request, principal, roles):
    if not hasattr(request.state,'dependency_deadline'):
        request.state.dependency_deadline=time.monotonic()+5
    role=next((r for r in roles if r in principal.roles),None)
    if role is None:
        raise HTTPException(403)
    await require_current_role(role)(request,principal)
    return role


def private_principal(request, caller, scope):
    verifier=request.app.state.auth_verifier
    if verifier.service(bearer(request),scope)!=caller:
        raise HTTPException(403)
    return verifier.user(bearer(request,'X-Delegated-Authorization'))
