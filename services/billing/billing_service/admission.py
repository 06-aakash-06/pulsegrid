"""Coordinator-owned HTTP admission composition; identity remains owner verified."""
import os
from pathlib import Path
from types import SimpleNamespace
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import compile_path
from pulsegrid_rate_limiter import RateLimiter,LimiterConfig
from pulsegrid_rate_limiter.adapter import AdmissionAdapter,VerifiedIdentity,rejection_metadata,rejection_response
from pulsegrid_rate_limiter.policies import RoutePolicy,operation_class_for


def policy_for(owner,method,path):
    if path.startswith('/internal/') or path in ('/metrics',):return 'internal_worker','internal'
    if path.startswith('/api/v1/auth/'):
        name=path.rsplit('/',1)[-1]
        return {'login':'auth_login','register':'auth_registration'}.get(name,'auth_session'),'auth'
    if owner in ('doctor','pharmacy') and method=='GET' and ('autocomplete' in path or path.endswith('/doctors') or path.endswith('/medicines') or path.endswith('/specialties')):
        return 'directory_search','directory'
    if owner=='emergency':return 'emergency_authenticated' if method=='POST' and path.endswith('/emergencies') else 'owner_read','emergency'
    if owner=='appointment' and method=='POST':return 'appointment_command','command'
    return 'owner_read','read' if method=='GET' else 'command'

class AdmissionRejected(Exception):
    def __init__(self,decision):self.decision=decision

class Middleware(BaseHTTPMiddleware):
    def finalize(self,request,response,decision=None):
        adapter=request.app.state.admission_adapter
        policy=adapter.classify(request)
        if policy is not None:
            outcome=decision.reason if decision is not None and not decision.allowed else getattr(request.state,'phase4_admission_outcome','accepted')
            labels={'owner':adapter.owner,'policy':getattr(request.state,'phase4_admission_policy',policy.policy_id),'outcome':outcome,'class':getattr(request.state,'phase6_operation_class',policy.operation_class),'state':getattr(request.state,'phase6_surge_mode','UNKNOWN')}
            try:request.app.state.phase4_observer.increment('pulsegrid_http_admission_requests_total',labels)
            except Exception:pass
        return response
    async def dispatch(self,request,call_next):
        adapter=request.app.state.admission_adapter
        for method,regex,template in request.app.state.admission_patterns:
            if request.method==method and regex.fullmatch(request.url.path):
                request.scope['route']=SimpleNamespace(path=template)
                break
        policy=adapter.classify(request)
        if policy and policy.policy=='internal_worker':
            decision=await adapter.admit(policy,{'source':adapter.deriver.source(request)},preauth=True,budgets={'source':(120,20000),'aggregate':(1200,200000)})
        else:
            decision=await adapter.pre_auth(request)
        request.state.phase6_operation_class=policy.operation_class if policy is not None else 'B'
        request.state.phase6_surge_mode=decision.surge_mode
        if not decision.allowed:return self.finalize(request,rejection_response(request,decision,error_response=request.app.state.admission_error_response),decision)
        policy=adapter.classify(request)
        if policy and policy.policy.startswith('auth_'):
            account=None
            if policy.policy=='auth_login':
                try:
                    body=await request.json()
                    from .authentication import LoginInput
                    account=adapter.deriver.digest('account',LoginInput.normalize_email(body.get('email','')))
                except Exception:
                    account=adapter.deriver.digest('account','invalid-account')
            decision=await adapter.post_auth(request,None,normalized_account_digest=account)
            request.state.phase6_surge_mode=decision.surge_mode
            if not decision.allowed:return self.finalize(request,rejection_response(request,decision,error_response=request.app.state.admission_error_response),decision)
        if policy and policy.policy=='internal_worker':
            # Read a candidate scope only to invoke the existing signature,
            # issuer/audience/expiry/caller verifier. The endpoint still enforces
            # its own exact scope and delegated resource checks afterwards.
            import jwt
            from .authorization import bearer
            try:
                token=bearer(request)
                scopes=jwt.decode(token,options={'verify_signature':False}).get('scopes',[])
                if not scopes or not isinstance(scopes[0],str):raise ValueError('invalid scoped token')
                caller=request.app.state.auth_verifier.service(token,scopes[0])
            except Exception:
                return self.finalize(request,await call_next(request))  # Existing owner returns its 401/403.
            async def verified_service(_):return VerifiedIdentity(caller,kind='service')
            decision=await adapter.post_auth(request,verified_service)
            request.state.phase6_surge_mode=decision.surge_mode
            if not decision.allowed:return self.finalize(request,rejection_response(request,decision,error_response=request.app.state.admission_error_response),decision)
        return self.finalize(request,await call_next(request))


def mount(app,owner,error_response):
    prefix=f'PULSEGRID_{owner.upper()}_PHASE4_'
    flag=os.environ.get(prefix+'ADMISSION_ENABLED','false')
    if flag not in ('true','false'):raise ValueError('Invalid admission flag')
    if flag=='false':return
    maximum=int(os.environ[prefix+'MAX_REPLICAS'])
    if not 1<=maximum<=4:raise ValueError('Reviewed deployment maximum is four processes')
    config=LimiterConfig(enabled=True,redis_endpoint=os.environ[prefix+'ADMISSION_URL'],redis_username='admission',redis_password=Path(os.environ[prefix+'ADMISSION_PASSWORD_FILE']).read_text().strip(),hmac_secret=Path(os.environ[prefix+'ADMISSION_HMAC_FILE']).read_bytes(),max_replicas=maximum)
    inventory={};patterns=[];exempt=[]
    paths={path:set(methods) for path,methods in app.openapi()['paths'].items()}
    pending=list(app.routes)
    seen=set()
    while pending:
        route=pending.pop()
        if id(route) in seen:continue
        seen.add(id(route))
        nested=getattr(route,'original_router',None)
        if nested is not None:pending.extend(nested.routes)
        if getattr(route,'path',None) and getattr(route,'methods',None):
            paths.setdefault(route.path,set()).update(method.lower() for method in route.methods)
    for path,methods in paths.items():
        for method in methods:
            if method.upper() not in ('GET','POST','PATCH','DELETE','PUT','HEAD','OPTIONS'):continue
            key=(method.upper(),path)
            if path.endswith(('/health/live','/health/ready')):exempt.append(key)
            else:
                policy,family=policy_for(owner,*key)
                inventory[key]=RoutePolicy(owner,policy,family,operation_class_for(owner,*key))
            patterns.append((key[0],compile_path(path)[0],path))
    for path in ('/health/live','/health/ready','/ping'):
        exempt.append(('GET',path));patterns.append(('GET',compile_path(path)[0],path))
    @app.exception_handler(AdmissionRejected)
    async def admission_rejected(request,error):
        return rejection_response(request,error.decision,error_response=error_response)
    app.state.admission_limiter=RateLimiter(config,observer=app.state.phase4_observer)
    app.state.admission_adapter=AdmissionAdapter(app.state.admission_limiter,owner,inventory,exempt_routes=exempt)
    app.state.admission_patterns=patterns
    app.state.admission_error_response=error_response
    app.add_middleware(Middleware)

async def post_user(request,principal):
    adapter=getattr(request.app.state,'admission_adapter',None)
    if adapter is None or getattr(request.state,'admission_principal_checked',False):return
    async def verified(_):return VerifiedIdentity(principal.user_id)
    policy=adapter.classify(request)
    staff_role=next((role for role in ('billing_staff', 'hospital_admin') if role in principal.roles),None)
    if policy and request.method in ('POST','PATCH','DELETE') and staff_role:
        from .authorization import require_current_role
        await require_current_role(staff_role)(request,principal)
        policy=RoutePolicy('billing','critical_staff','command',policy.operation_class)
        decision=await adapter.admit(policy,{'principal':adapter.deriver.principal(principal.user_id)})
    else:
        decision=await adapter.post_auth(request,verified)
    if policy is not None:
        request.state.phase4_admission_policy=policy.policy_id
        request.state.phase6_operation_class=policy.operation_class
        request.state.phase6_surge_mode=decision.surge_mode
    if not decision.allowed:
        request.state.phase4_admission_outcome=decision.reason
        raise AdmissionRejected(decision)
    request.state.admission_principal_checked=True

async def close(app):
    limiter=getattr(app.state,'admission_limiter',None)
    if limiter is not None:await limiter.close()
