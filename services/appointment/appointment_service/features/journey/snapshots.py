"""Bounded service-authenticated snapshot reads outside local transactions."""
import asyncio
import json
import time
from datetime import datetime
from urllib.parse import urlencode
import httpx
from ...authorization import service_token
from ...wire import ID, Version, Time
from pydantic import TypeAdapter


class SnapshotUnavailable(TimeoutError):
    pass


def validate(snapshot, owner, aid, pid):
    if not isinstance(snapshot, dict) or snapshot.get('appointment_id') != str(aid) or snapshot.get('patient_id') != str(pid):
        raise SnapshotUnavailable('identity_mismatch')
    TypeAdapter(Version).validate_python(snapshot['revision'])
    observed = TypeAdapter(Time).validate_python(snapshot['observed_at'])
    from ... import operations as op
    if not 0 <= (op.now()-observed).total_seconds() <= 5:
        raise SnapshotUnavailable('source_stale')
    if owner == 'records' and snapshot.get('consultation'):
        c = snapshot['consultation']; TypeAdapter(ID).validate_python(c['id'])
        TypeAdapter(Version).validate_python(c['version']); TypeAdapter(ID).validate_python(snapshot['doctor_id'])
        if c['status'] not in ('draft', 'finalized') or type(c['record_revision']) is not int or c['record_revision'] < 0:
            raise SnapshotUnavailable('source_invalid')
    if owner == 'billing' and snapshot.get('invoice'):
        invoice = snapshot['invoice']
        TypeAdapter(ID).validate_python(invoice['id']); TypeAdapter(Version).validate_python(invoice['version'])
        amounts = [invoice[k] for k in ('total_minor','paid_minor','balance_minor')]
        if (invoice['currency'] != 'INR' or invoice['status'] not in ('open','paid') or
            any(type(n) is not int or not 0 <= n <= 9007199254740991 for n in amounts) or
            amounts[0]-amounts[1] != amounts[2] or
            invoice['status']=='paid' and (amounts[0]==0 or amounts[2]!=0)):
            raise SnapshotUnavailable('source_invalid')
    return snapshot


class SnapshotClient:
    def __init__(self, transport=None):
        self.transport = transport
        self.failures = {}; self.open_until = {}

    async def request(self, request, owner, scope, path, method='GET', body=None):
        if self.open_until.get(owner, 0) > time.monotonic():
            raise SnapshotUnavailable('owner_unavailable')
        headers = {'Authorization':'Bearer '+service_token(request.app.state.auth_config,scope,owner),
            'X-Request-ID':str(request.state.request_id),'X-Correlation-ID':str(request.state.correlation_id)}
        if getattr(request.state, 'traceparent', None): headers['traceparent']=request.state.traceparent
        for attempt in range(2):
            try:
                async with asyncio.timeout(1):
                    async with httpx.AsyncClient(timeout=1, trust_env=False, follow_redirects=False,
                                                transport=self.transport) as client:
                        async with client.stream(method, 'http://'+owner+':8000'+path,headers=headers,json=body) as response:
                            if response.status_code != 200:
                                raise SnapshotUnavailable('source_changed' if response.status_code == 409 else 'owner_unavailable')
                            raw = bytearray()
                            async for chunk in response.aiter_bytes():
                                raw.extend(chunk)
                                if len(raw)>262144: raise SnapshotUnavailable('source_too_large')
                result = json.loads(raw); self.failures[owner]=0
                return result
            except (httpx.HTTPError, TimeoutError, ValueError, SnapshotUnavailable):
                self.failures[owner]=self.failures.get(owner,0)+1
                if self.failures[owner]>=5: self.open_until[owner]=time.monotonic()+15
                if attempt: raise SnapshotUnavailable('owner_unavailable') from None
                await asyncio.sleep(.05)
        raise SnapshotUnavailable('owner_unavailable')

    async def episode(self, request, owner, aid, pid, prescription_id=None):
        query={'patient_id':str(pid),'limit':'100'}
        if prescription_id: query['prescription_id']=str(prescription_id)
        aggregate=None; seen=set()
        for _ in range(10):
            page = await self.request(request,owner,'workflow:'+owner+'-read',
                '/internal/v1/appointments/'+str(aid)+'/workflow-snapshot?'+urlencode(query))
            if not isinstance(page,dict) or set(page)!= {'snapshot','next_cursor'}:
                raise SnapshotUnavailable('source_invalid')
            snapshot=validate(page['snapshot'],owner,aid,pid)
            paths = [('consultation','prescription','items')] if owner=='records' else (
                [('fulfillment','items'),('fulfillment','reservations'),('fulfillment','dispensings')] if owner=='pharmacy' else [('invoice','charge_source_keys')])
            def collection(data,path,bounded=True):
                for key in path[:-1]:
                    data=data.get(key)
                    if data is None: return None
                result=data.get(path[-1])
                if not isinstance(result,list) or bounded and len(result)>100: raise SnapshotUnavailable('source_invalid')
                return result
            # Compare the scalar membership/version header on every page.
            scalar=json.loads(json.dumps(snapshot));scalar.pop('observed_at')
            if scalar.get('fulfillment'): scalar['fulfillment'].pop('observed_at',None)
            if prescription_id and snapshot.get('prescription_id') != str(prescription_id):
                raise SnapshotUnavailable('identity_mismatch')
            for path in paths:
                data=scalar
                for key in path[:-1]:
                    data=data.get(key)
                    if data is None: break
                if data is not None: data[path[-1]]=[]
            if aggregate is None:
                aggregate=json.loads(json.dumps(snapshot)); header=scalar
            else:
                if scalar != header: raise SnapshotUnavailable('source_changed')
                for path in paths:
                    values=collection(snapshot,path)
                    if values is not None: collection(aggregate,path,False).extend(values)
            for path in paths: collection(snapshot,path)
            cursor=page['next_cursor']
            if cursor is None:
                for path in paths:
                    values=collection(aggregate,path,False)
                    if values is not None and len({json.dumps(x,sort_keys=True) for x in values}) != len(values):
                        raise SnapshotUnavailable('source_invalid')
                return aggregate
            if not isinstance(cursor,str) or not cursor or len(cursor)>2048 or cursor in seen:
                raise SnapshotUnavailable('source_invalid')
            seen.add(cursor);query['cursor']=cursor
        raise SnapshotUnavailable('source_too_large')
