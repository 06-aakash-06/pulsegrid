import pytest
from appointment_service import phase3_core as core
from appointment_service.features.waitlist.registration import register_routes
from ..test_api import api, BOOK


@pytest.fixture
def waitlist_api(api):
    client,headers,token,fixture=api
    # Mount the isolated feature before the legacy dynamic route in this test app.
    existing=list(client.app.router.routes)
    client.app.router.routes.clear()
    register_routes(client.app,core)
    client.app.router.routes.extend(existing)
    return api


def join(client,headers,pid='12',**body):
    return client.post('/api/v1/appointments/waitlists',json={**BOOK,'patient_id':pid,**body},headers=headers)


def test_http_scope_etag_cursor_replay(waitlist_api):
    c,h,_,_=waitlist_api
    assert c.post('/api/v1/appointments',json=BOOK,headers=h()).status_code==201
    own=h(sub='12',pid='12')
    first=join(c,own)
    assert first.status_code==201,first.text
    value=first.json();eid=value['id']
    assert first.headers['etag']=='"1"' and first.headers['cache-control']=='no-store'
    assert join(c,own).json()==value
    assert join(c,h(sub='12',pid='12')).json()['error']['code']=='already_waiting'
    assert join(c,h(),pid='11').json()['error']['code']=='already_booked'
    assert c.get('/api/v1/appointments/waitlists/'+eid,headers=h()).status_code==404
    assert c.get('/api/v1/appointments/waitlists',headers=h()).json()['items']==[]
    assert c.get('/api/v1/appointments/waitlists?patient_id=12',headers=h()).status_code==404
    doctor=h(sub='101',roles=('doctor',),pid=None)
    assert c.get('/api/v1/appointments/waitlists/'+eid,headers=doctor).json()==value
    assert c.get('/api/v1/appointments/waitlists/'+eid,headers=h(sub='102',roles=('doctor',),pid=None)).status_code==404
    staff=h(sub='300',roles=('receptionist',),pid=None)
    assert join(c,staff,pid='13').status_code==201
    page=c.get('/api/v1/appointments/waitlists?limit=1',headers=staff).json()
    assert page['items']==[value] and page['next_cursor']
    assert len(c.get('/api/v1/appointments/waitlists',params={'cursor':page['next_cursor'],'limit':1},headers=staff).json()['items'])==1
    assert c.get('/api/v1/appointments/waitlists',params={'cursor':page['next_cursor'],'slot_id':'1'},headers=staff).status_code==400
    assert c.get('/api/v1/appointments/waitlists',params={'cursor':page['next_cursor']},headers=own).status_code==400
    path='/api/v1/appointments/waitlists/'+eid+'/withdraw'
    for version,status in ((None,428),('1',400),('"8"',412)):
        headers=h(sub='12',pid='12')
        if version:
            headers['If-Match']=version
        assert c.post(path,json={'reason':'synthetic'},headers=headers).status_code==status
    headers=h(sub='12',pid='12');headers['If-Match']='"1"'
    withdrawn=c.post(path,json={'reason':'synthetic'},headers=headers)
    assert withdrawn.status_code==200 and withdrawn.json()['state']=='withdrawn'
    assert withdrawn.headers['etag']=='"2"'
    assert c.post(path,json={'reason':'synthetic'},headers=headers).json()==withdrawn.json()
    headers['Authorization']=h(sub='12',pid='12',auth_version=2)['Authorization']
    assert c.post(path,json={'reason':'synthetic'},headers=headers).status_code==403


@pytest.mark.parametrize('case,status',[
    ('anonymous',401),('wrong_role',403),('other_patient',404),('inactive',422),
    ('numeric_id',422),('extra',422),('revision',409),('free',409),('query',422)])
def test_http_join_failures(waitlist_api,case,status):
    c,h,_,fixture=waitlist_api
    c.post('/api/v1/appointments',json=BOOK,headers=h())
    headers=h(sub='12',pid='12');body={**BOOK,'patient_id':'12'};url='/api/v1/appointments/waitlists'
    if case=='anonymous':
        headers={}
    elif case=='wrong_role':
        headers=h(roles=('ops',))
    elif case=='other_patient':
        headers=h()
    elif case=='inactive':
        fixture.active=False
    elif case=='numeric_id':
        body['patient_id']=12
    elif case=='extra':
        body['priority']=1
    elif case=='revision':
        body['expected_schedule_revision']=2
    elif case=='free':
        body['slot_id']='2'
    elif case=='query':
        url+='?unknown=1'
    response=c.post(url,json=body,headers=headers)
    assert response.status_code==status,response.text
    assert 'error' in response.json()


def test_list_rejects_unknown_duplicate_and_bad_cursor(waitlist_api):
    c,h,_,_=waitlist_api
    for query,status in [('?unknown=1',422),('?state=waiting&state=waiting',422),('?state=offered',422),('?cursor=bad!',400)]:
        assert c.get('/api/v1/appointments/waitlists'+query,headers=h()).status_code==status


def test_status_counts_only_and_staff_scope(waitlist_api):
    import asyncio
    from .test_waitlist import schema
    c,h,_,_=waitlist_api
    asyncio.run(schema(c.app.state.database))
    c.post('/api/v1/appointments',json=BOOK,headers=h())
    join(c,h(sub='12',pid='12'))
    result=c.get('/api/v1/appointments/waitlist-slots/1',headers=h())
    assert result.status_code==200,result.text
    assert result.json()['waiting_count']==1 and not result.json()['promotion_pending']
    assert set(result.json())=={'slot_id','waiting_count','promotion_pending','accepted_revision','observed_at'}
    assert c.get('/api/v1/appointments/waitlist-slots/1',headers=h(sub='102',roles=('doctor',),pid=None)).status_code==404
    assert c.get('/api/v1/appointments/waitlist-slots/1',headers=h(sub='101',roles=('doctor',),pid=None)).status_code==200
