import asyncio
from dataclasses import replace
import pytest
from fastapi import FastAPI, Request, HTTPException
from httpx import AsyncClient, ASGITransport
from pulsegrid_rate_limiter import *
SECRET = b'synthetic-test-key-not-deployment!'*2

def config(server):
    return LimiterConfig(enabled=True, hmac_secret=SECRET, redis_endpoint=server.url)

def bucket(cap=4):
    return BucketRequest(IdentityDeriver(SECRET).digest('principal', 'test-principal'),
                         BucketSpec('test', cap, 4, 1, cap*250000+1000))

# Test-only matched route; no production middleware or auth implementation edits.
def request(path='/search', method='GET', headers=(), peer='127.0.0.1'):
    class Route: pass
    route=Route(); route.path=path
    return Request({'type':'http','method':method,'path':path,'headers':headers,
        'client':(peer,1234),'route':route})

async def user(req): return VerifiedIdentity('1')
async def staff(req): return VerifiedIdentity('2',current_staff=True)

def test_spoofing_does_not_choose_identity():
    derive=IdentityDeriver(SECRET)
    a=request(headers=[(b'x-forwarded-for',b'198.51.100.1'),(b'x-user-id',b'99')])
    b=request(headers=[(b'x-forwarded-for',b'198.51.100.2'),(b'authorization',b'Bearer fake')])
    assert derive.source(a)==derive.source(b)
    assert derive.source(a)!=derive.source(request(peer='127.0.0.2'))
    assert derive.source(request(peer='garbage'))==derive.source(request(peer='another-garbage'))
    assert derive.source(request(peer='::ffff:127.0.0.1'))==derive.source(a)
    assert derive.digest('source','1')!=derive.principal('1')

@pytest.mark.parametrize('value',['0','01','-1','1:admin','９','',str(2**63),1])
def test_invalid_principal(value):
    with pytest.raises(InvalidConfiguration): IdentityDeriver(SECRET).principal(value)

async def test_distinct_verified_principals_and_preauth(redis_server):
    l=RateLimiter(config(redis_server))
    adapter=AdmissionAdapter(l,'doctor',{('GET','/search'):RoutePolicy('doctor','directory_search','search')})
    try:
        req=request()
        assert (await adapter.pre_auth(req)).allowed
        assert (await adapter.post_auth(req,user)).allowed
        async def other(req): return VerifiedIdentity('2')
        assert (await adapter.post_auth(req,other)).allowed
        keys=await l.redis.keys('pg:admission:*')
        assert len(keys)==5 # 2 preauth + 2 principals + post aggregate
        assert not any(b'Bearer' in key or b'127.0.0.1' in key for key in keys)
    finally: await l.close()

async def test_malformed_jwt_is_not_principal_and_auth_errors_preserved(redis_server):
    l=RateLimiter(config(redis_server))
    a=AdmissionAdapter(l,'doctor',{('GET','/search'):RoutePolicy('doctor','directory_search','search')})
    async def invalid(req): raise HTTPException(401,headers={'WWW-Authenticate':'Bearer'})
    try:
        req=request(headers=[(b'authorization',b'Bearer not.a.jwt')])
        assert (await a.pre_auth(req)).allowed
        with pytest.raises(HTTPException) as exc: await a.post_auth(req,invalid)
        assert exc.value.status_code==401
        async def unverified(req): return {'sub':'1','roles':['doctor']}
        assert (await a.post_auth(req,unverified)).reason=='unavailable'
    finally: await l.close()

async def test_staff_emergency_isolation(redis_server):
    l=RateLimiter(config(redis_server))
    routes={('POST','/public'):RoutePolicy('emergency','emergency_public','submission'),
            ('POST','/user'):RoutePolicy('emergency','emergency_authenticated','submission'),
            ('POST','/staff'):RoutePolicy('emergency','emergency_staff','mutation')}
    a=AdmissionAdapter(l,'emergency',routes)
    try:
        results=[await a.post_auth(request('/public','POST'),user) for _ in range(20)]
        assert sum(r.allowed for r in results)==5
        assert (await a.post_auth(request('/user','POST'),user)).allowed
        assert (await a.post_auth(request('/staff','POST'),staff)).allowed
        assert (await a.post_auth(request('/staff','POST'),user)).reason=='unavailable'
    finally: await l.close()

async def test_unknown_and_exempt_routes(redis_server):
    l=RateLimiter(config(redis_server))
    a=AdmissionAdapter(l,'records',{},exempt_routes={('GET','/health')})
    try:
        assert (await a.pre_auth(request('/health'))).allowed
        assert (await a.pre_auth(request('/anything','OPTIONS'))).allowed
        assert not await l.redis.keys('pg:admission:*')
        for _ in range(31): result=await a.pre_auth(request('/unregistered'))
        assert not result.allowed
    finally: await l.close()

async def test_login_digest_owner_supplied_and_generic_error(redis_server):
    l=RateLimiter(config(redis_server))
    a=AdmissionAdapter(l,'patient',{('POST','/login'):RoutePolicy('patient','auth_login','login')})
    try:
        req=request('/login','POST')
        assert (await a.post_auth(req,user)).reason=='unavailable'
        digest=a.deriver.digest('account','normalized-owner-test-input')
        assert (await a.post_auth(req,user,normalized_account_digest=digest)).allowed
        assert (await a.post_auth(req,user,normalized_account_digest='spoof')).reason=='unavailable'
    finally: await l.close()

async def test_http_retry_envelope_and_business_failure_consumes(redis_server):
    l=RateLimiter(config(redis_server))
    app=FastAPI()
    @app.post('/command')
    async def command(req:Request):
        result=await l.admit([bucket(cap=4)])
        rejection=rejection_response(req,result)
        if rejection: return rejection
        raise HTTPException(422) # admitted invalid business command is charged
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            for _ in range(4): assert (await client.post('/command')).status_code==422
            res=await client.post('/command')
            assert res.status_code==429 and int(res.headers['Retry-After']) >= 1
            assert res.json()['error']['code']=='rate_limited'
            assert res.headers['Cache-Control']=='no-store'
        unavailable=Admission(False,1000,0,'local','unavailable')
        assert rejection_response(request(),unavailable).status_code==503
        assert rejection_metadata(unavailable)[2]['Retry-After']=='1'
    finally: await l.close()
