"""HTTP contract/auth tests with PostgreSQL and explicit remote API fixtures."""
import asyncio
import time
from uuid import uuid4
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from fastapi.testclient import TestClient
from appointment_service.authorization import AuthConfig, Verifier
from appointment_service.database import Database
from appointment_service.main import create_app
from appointment_service.wire import Identity, PatientStatus, ProposalContext
from test_concurrency import seed


@pytest.fixture
def api(database,monkeypatch):
    from appointment_service import dependencies
    async def accepted(request,p):
        if p.auth_version!=1:
            from fastapi import HTTPException
            raise HTTPException(403)
        return p
    monkeypatch.setattr(dependencies,'require_current_role',lambda role:accepted)
    user_key=generate_private_key(public_exponent=65537,key_size=2048)
    service_key=generate_private_key(public_exponent=65537,key_size=2048)
    verifier=Verifier(AuthConfig())
    verifier.user_keys={'test-user':user_key.public_key()}
    verifier.service_keys={f'test-{owner}':service_key.public_key() for owner in ('records','doctor','billing')}
    verifier.service_key_owners={f'test-{owner}':owner for owner in ('records','doctor','billing')}
    app=create_app(database)
    app.state.auth_verifier=verifier
    class FixtureClient:
        active=True
        active_doctor=True
        async def get(self,request,p,owner,path,scope,schema):
            if schema is Identity:
                return Identity(doctor_id='1',staff_user_id='101',active=self.active_doctor,version=1)
            if schema is PatientStatus:
                return PatientStatus(patient_id=path.split('/')[-2],active=self.active,version=1)
            if schema is ProposalContext:
                return schema.model_validate(self.proposal)
            raise AssertionError('Unexpected dependency')
    fixture=FixtureClient()
    app.state.domain_client=fixture
    async def initialize():
        db=Database(database)
        await db.start()
        try:
            await seed(db)
        finally:
            await db.close()
    asyncio.run(initialize())
    def token(sub='11',roles=('patient',),pid='11',auth_version=1,service=False,scope='appointments:clinical-hold',caller='records'):
        t=int(time.time())
        claims={'iss':'pulsegrid-patient','aud':'pulsegrid-api','sub':sub,'jti':uuid4().hex,
            'iat':t,'nbf':t,'exp':t+60,'token_use':'access','roles':list(roles),'patient_id':pid,'auth_version':auth_version}
        if service:
            claims.update(iss='pulsegrid-service:'+caller,aud='pulsegrid-internal:appointment',sub=caller,token_use='service',scopes=[scope])
        return jwt.encode(claims,service_key if service else user_key,algorithm='RS256',
            headers={'kid':'test-'+caller if service else 'test-user'})
    def headers(**kwargs):
        return {'Authorization':'Bearer '+token(**kwargs),'Idempotency-Key':uuid4().hex}
    with TestClient(app) as client:
        yield client,headers,token,fixture


BOOK={'patient_id':'11','slot_id':'1','expected_schedule_revision':1}


def test_public_book_get_list_cancel_and_replay(api):
    c,h,_,_=api
    headers=h()
    result=c.post('/api/v1/appointments',json=BOOK,headers=headers)
    assert result.status_code==201,result.text
    assert result.headers['etag']=='"1"'
    a=result.json(); aid=a['id']
    assert set(a)=={'id','journey_id','patient_id','doctor_id','slot_id','starts_at','ends_at','state','version'}
    assert c.get('/api/v1/appointments/'+aid,headers=h()).json()==a
    assert c.get('/api/v1/appointments',headers=h()).json()['items']==[a]
    cancel=h(); cancel['If-Match']='"1"'
    assert c.post('/api/v1/appointments/'+aid+'/cancel',json={'reason':'test'},headers=cancel).status_code==200
    replay=c.post('/api/v1/appointments',json=BOOK,headers=headers)
    assert replay.json()==a and replay.headers['etag']=='"1"'
    assert c.post('/api/v1/appointments',json={**BOOK,'slot_id':'2'},headers=headers).status_code==409


@pytest.mark.parametrize('case',('no_token','ops','other_patient','revoked','inactive','numeric_id','boolean_revision','extra_field','missing_key'))
def test_auth_reference_and_input_failures(api,case):
    c,h,_,fixture=api
    headers=h(); body=dict(BOOK); expected=422
    if case=='no_token': headers={}; expected=401
    elif case=='ops': headers=h(roles=('ops',)); expected=403
    elif case=='other_patient': headers=h(sub='12',pid='12'); expected=404
    elif case=='revoked': headers=h(auth_version=2); expected=403
    elif case=='inactive': fixture.active=False
    elif case=='numeric_id': body['patient_id']=11
    elif case=='boolean_revision': body['expected_schedule_revision']=True
    elif case=='extra_field': body['state']='confirmed'
    elif case=='missing_key': headers.pop('Idempotency-Key')
    result=c.post('/api/v1/appointments',json=body,headers=headers)
    assert result.status_code==expected,result.text
    assert 'error' in result.json()
    assert c.get('/api/v1/appointments',headers=h()).json()['items']==[]


def test_scope_preconditions_pagination_and_availability(api):
    c,h,_,_=api
    a=c.post('/api/v1/appointments',json=BOOK,headers=h()).json()
    aid=a['id']
    assert c.get('/api/v1/appointments/'+aid,headers=h(sub='12',pid='12')).status_code==404
    assert c.get('/api/v1/appointments',headers=h(sub='12',pid='12')).json()['items']==[]
    assert c.get('/api/v1/appointments',headers=h(sub='101',roles=('doctor',),pid=None)).json()['items']==[a]
    assert c.get('/api/v1/appointments/'+aid,headers=h(sub='102',roles=('doctor',),pid=None)).status_code==404
    for version,expected in ((None,428),('1',400),('"9"',412)):
        headers=h()
        if version: headers['If-Match']=version
        assert c.post('/api/v1/appointments/'+aid+'/cancel',json={'reason':'test'},headers=headers).status_code==expected
    assert c.get('/api/v1/appointments?unknown=1',headers=h()).status_code==422
    assert c.get('/api/v1/appointments?cursor=bad!',headers=h()).status_code==400
    b=c.post('/api/v1/appointments',json={**BOOK,'slot_id':'2'},headers=h()).json()
    first=c.get('/api/v1/appointments?limit=1',headers=h()).json()
    assert len(first['items'])==1 and first['next_cursor']
    second=c.get('/api/v1/appointments',params={'limit':1,'cursor':first['next_cursor']},headers=h()).json()
    assert second['items']==[b]
    assert c.get('/api/v1/appointments',params={'limit':1,'cursor':first['next_cursor'],'doctor_id':'1'},headers=h()).status_code==400
    availability=c.get('/api/v1/appointments/availability',params={'doctor_id':'1','from':a['starts_at'],'to':b['ends_at']},headers=h())
    assert availability.status_code==200 and availability.json()['slots']==[]
    assert c.get('/api/v1/appointments/availability',params={'doctor_id':'1','from':'2026-10-12T10:00:00+05:30','to':'2026-10-13T10:00:00Z'},headers=h()).status_code==422


def test_private_service_auth_assignment_and_hold(api):
    c,h,t,_=api
    a=c.post('/api/v1/appointments',json=BOOK,headers=h()).json()
    path='/internal/v1/appointments/'+a['id']+'/clinical-hold'
    assert c.post(path,json={'consultation_id':'900'},headers=h()).status_code==401
    headers={'Authorization':'Bearer '+t(service=True),'X-Delegated-Authorization':'Bearer '+t(sub='101',roles=('doctor',),pid=None),
        'Idempotency-Key':uuid4().hex,'If-Match':'"1"'}
    acquired=c.post(path,json={'consultation_id':'900'},headers=headers)
    assert acquired.status_code==200,acquired.text
    assert acquired.json()['clinical_hold']=='active'
    assert c.post(path,json={'consultation_id':'900'},headers=headers).json()==acquired.json()
    change=h(); change['If-Match']='"2"'
    assert c.post('/api/v1/appointments/'+a['id']+'/cancel',json={'reason':'test'},headers=change).json()['error']['code']=='clinical_hold'
    final=dict(headers,**{'If-Match':'"2"','Idempotency-Key':uuid4().hex})
    finalized=c.post(path+'/finalize',json={'consultation_id':'900'},headers=final)
    assert finalized.json()['clinical_hold']=='finalized' and finalized.headers['etag']=='"3"'
    bad=dict(headers,**{'X-Delegated-Authorization':'Bearer '+t(sub='102',roles=('doctor',),pid=None),'Idempotency-Key':uuid4().hex})
    assert c.post(path,json={'consultation_id':'901'},headers=bad).status_code==404
    scope=dict(headers,Authorization='Bearer '+t(service=True,scope='appointments:billing-context'))
    assert c.post(path,json={'consultation_id':'900'},headers=scope).status_code==403


def test_endpoint_reschedule_keeps_id_and_moves_slot(api):
    c,h,_,_=api
    a=c.post('/api/v1/appointments',json=BOOK,headers=h()).json()
    headers=h(); headers['If-Match']='"1"'
    result=c.post('/api/v1/appointments/'+a['id']+'/reschedule',json={'target_slot_id':'2','expected_schedule_revision':1},headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['id']==a['id'] and result.json()['slot_id']=='2'
    assert result.headers['etag']=='"2"'


def test_inactive_doctor_prevents_booking_and_staff_management(api):
    c,h,_,fixture=api
    fixture.active_doctor=False
    result=c.post('/api/v1/appointments',json=BOOK,headers=h())
    assert result.status_code==422 and result.json()['error']['code']=='invalid_reference'
    fixture.active_doctor=True
    staff=h(sub='300',roles=('receptionist',),pid=None)
    booked=c.post('/api/v1/appointments',json=BOOK,headers=staff)
    assert booked.status_code==201
    aid=booked.json()['id']
    staff['If-Match']='"1"'
    assert c.post('/api/v1/appointments/'+aid+'/cancel',json={'reason':'staff requested'},headers=staff).status_code==200
    assert c.post('/api/v1/appointments',json={**BOOK,'patient_id':'12'},headers=h(sub='12',pid='12')).status_code==201


def test_schedule_decision_endpoints_and_private_leaves(api):
    from appointment_service import operations as op
    from datetime import timedelta
    c,h,t,fixture=api
    start=op.now()+timedelta(days=4)
    fixture.proposal={'proposal':{'id':'500','doctor_id':'1','revision':2,'status':'pending','timezone':'UTC',
        'slot_minutes':30,'intervals':[{'starts_at':op.wire_time(start),'ends_at':op.wire_time(start+timedelta(hours=1))}],
        'conflicts':[],'version':1},'staff_user_id':'101','active':True,'doctor_version':1}
    own=h(sub='101',roles=('doctor',),pid=None)
    result=c.post('/api/v1/appointments/schedule-decisions',json={'doctor_id':'1','proposal_id':'500','expected_accepted_revision':1},headers=own)
    assert result.status_code==201,result.text
    assert result.json()['state']=='accepted'
    assert c.get('/api/v1/appointments/schedule-decisions/500',headers=own).json()==result.json()
    assert c.get('/api/v1/appointments/schedule-decisions/500',headers=h()).status_code==403
    private={'Authorization':'Bearer '+t(service=True,caller='doctor',scope='schedule-decisions:read'),
        'X-Delegated-Authorization':'Bearer '+t(sub='101',roles=('doctor',),pid=None)}
    assert c.get('/internal/v1/schedule-decisions/500',headers=private).json()==result.json()
    private['Authorization']='Bearer '+t(service=True,caller='doctor',scope='schedules:status')
    status=c.get('/internal/v1/doctors/1/operational-status',headers=private)
    assert status.status_code==200,status.text
    assert status.json()['bookable_slot_count']==2 and status.json()['confirmed_booking_count']==0
    assert c.get('/internal/v1/doctors/999/operational-status',headers=private).status_code==404
    private['X-Delegated-Authorization']='Bearer '+t(sub='300',roles=('hospital_admin',),pid=None)
    absent=c.get('/internal/v1/doctors/999/operational-status',headers=private)
    assert absent.json()=={'doctor_id':'999','bookable_slot_count':0,'confirmed_booking_count':0,'version':1}


def test_private_read_contexts_no_callbacks_and_no_broad_clinical_access(api):
    c,h,t,fixture=api
    a=c.post('/api/v1/appointments',json=BOOK,headers=h()).json()
    aid=a['id']
    class ForbiddenClient:
        async def get(self,*args):
            raise AssertionError('Private leaf called another service')
    c.app.state.domain_client=ForbiddenClient()
    private={'Authorization':'Bearer '+t(service=True,scope='appointments:consultation-context'),
        'X-Delegated-Authorization':'Bearer '+t()}
    ctx=c.get('/internal/v1/appointments/'+aid+'/consultation-context',headers=private)
    assert ctx.status_code==200 and ctx.json()['doctor_user_id']=='101'
    private['X-Delegated-Authorization']='Bearer '+t(sub='300',roles=('hospital_admin',),pid=None)
    assert c.get('/internal/v1/appointments/'+aid+'/consultation-context',headers=private).status_code==404
    private={'Authorization':'Bearer '+t(service=True,caller='billing',scope='appointments:billing-context'),
        'X-Delegated-Authorization':'Bearer '+t(sub='301',roles=('billing_staff',),pid=None)}
    billing=c.get('/internal/v1/appointments/'+aid+'/billing-context',headers=private)
    assert billing.status_code==200 and set(billing.json())=={'appointment_id','patient_id','state','version'}
    private['X-Delegated-Authorization']='Bearer '+t()
    assert c.get('/internal/v1/appointments/'+aid+'/billing-context',headers=private).status_code==403
