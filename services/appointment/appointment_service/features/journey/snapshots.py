"""Bounded service-authenticated snapshot reads outside local transactions."""
import asyncio
from email.utils import parsedate_to_datetime
import json
import random
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
import httpx
from ...authorization import service_token
from ...wire import ID, Version, Time
from .resilience import CircuitBreaker, CircuitOpen
from pydantic import TypeAdapter


class SnapshotUnavailable(TimeoutError):
    pass


class SnapshotUnknown(SnapshotUnavailable):
    """A healthy owner has no identity-bound resource yet; do not trip its circuit."""


class _NoRetryFailure(SnapshotUnavailable):
    """A dependency failure whose Retry-After cannot fit the read deadline."""


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
    TOTAL_TIMEOUT_SECONDS = 1.0
    CONNECT_TIMEOUT_SECONDS = 0.250
    READ_TIMEOUT_SECONDS = 0.500
    BULKHEAD_SIZE = 2
    BULKHEAD_WAIT_SECONDS = 0.050
    MAX_RESPONSE_BYTES = 262144

    def __init__(self, transport=None, *, observer=None, clock=time.monotonic,
                 sleep=asyncio.sleep, jitter=random.random):
        self.transport = transport
        self.observer = observer
        self.clock = clock
        self.sleep = sleep
        self.jitter = jitter
        self.client = None
        self.breakers = {}
        self.bulkheads = {}
        self.in_flight = {}

    async def start(self):
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=self.CONNECT_TIMEOUT_SECONDS,
                                      read=self.READ_TIMEOUT_SECONDS,
                                      write=self.READ_TIMEOUT_SECONDS,
                                      pool=self.BULKHEAD_WAIT_SECONDS),
                limits=httpx.Limits(max_connections=6, max_keepalive_connections=3),
                trust_env=False, follow_redirects=False, transport=self.transport)

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def _observer(self, request):
        return self.observer or getattr(request.app.state, 'phase4_observer', None)

    def _increment(self, request, name, labels):
        observer = self._observer(request)
        if observer is not None:
            try: observer.increment(name, labels)
            except Exception: pass

    def _gauge(self, request, name, value, labels):
        observer = self._observer(request)
        if observer is not None:
            try: observer.gauge(name, value, labels)
            except Exception: pass

    def _breaker(self, request, owner):
        breaker = self.breakers.get(owner)
        if breaker is None:
            observer = self._observer(request)
            def state_changed(state):
                if observer is not None:
                    try:
                        observer.gauge('pulsegrid_dependency_circuit_breaker_state',
                            {'CLOSED': 1, 'OPEN': 2, 'HALF_OPEN': 3}[state],
                            {'dependency': owner, 'state': state})
                        if state == 'OPEN':
                            observer.increment('pulsegrid_dependency_circuit_breaker_open_total',
                                               {'dependency': owner, 'state': state})
                    except Exception: pass
            breaker = CircuitBreaker(clock=self.clock, on_state=state_changed)
            self.breakers[owner] = breaker
            state_changed(breaker.state)
        return breaker

    def _bulkhead(self, owner):
        semaphore = self.bulkheads.get(owner)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.BULKHEAD_SIZE)
            self.bulkheads[owner] = semaphore
            self.in_flight[owner] = 0
        return semaphore

    @staticmethod
    def _retry_after_seconds(response):
        value = response.headers.get('Retry-After')
        if not value:
            return None
        try:
            seconds = float(value)
            if seconds < 0: return None
            return seconds
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                if when.tzinfo is None: when = when.replace(tzinfo=timezone.utc)
                return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    async def request(self, request, owner, scope, path, *, validate_response=None):
        """Read one optional owner snapshot; only this GET boundary is retried."""
        if owner not in ('records', 'pharmacy', 'billing'):
            raise ValueError('Snapshot owner is not in the reviewed inventory')
        started = self.clock()
        semaphore = self._bulkhead(owner)
        breaker = self._breaker(request, owner)
        permit = None
        acquired = False
        in_flight = False
        failure_recorded = False
        labels = {'dependency': owner}

        async def record_failure(timeout=False):
            nonlocal failure_recorded
            if failure_recorded: return
            failure_recorded = True
            await breaker.failed(permit)
            self._increment(request, 'pulsegrid_dependency_failures_total',
                            {'dependency': owner, 'outcome': 'timeout' if timeout else 'failure'})
            if timeout:
                self._increment(request, 'pulsegrid_dependency_timeouts_total',
                                {'dependency': owner, 'outcome': 'timeout'})
            self._increment(request, 'pulsegrid_graceful_degradations_total',
                            {'dependency': owner, 'outcome': 'timeout' if timeout else 'dependency_failure'})

        try:
            async with asyncio.timeout(self.TOTAL_TIMEOUT_SECONDS):
                try:
                    permit = await breaker.acquire()
                except CircuitOpen:
                    self._increment(request, 'pulsegrid_graceful_degradations_total',
                                    {'dependency': owner, 'outcome': 'circuit_open'})
                    raise SnapshotUnavailable('owner_unavailable') from None
                try:
                    await asyncio.wait_for(semaphore.acquire(), self.BULKHEAD_WAIT_SECONDS)
                except TimeoutError:
                    await breaker.cancelled(permit)
                    self._increment(request, 'pulsegrid_bulkhead_rejections_total',
                                    {'dependency': owner, 'outcome': 'saturated'})
                    self._increment(request, 'pulsegrid_graceful_degradations_total',
                                    {'dependency': owner, 'outcome': 'bulkhead_full'})
                    raise SnapshotUnavailable('dependency_saturated') from None
                acquired = True
                self.in_flight[owner] += 1
                in_flight = True
                self._gauge(request, 'pulsegrid_bulkhead_in_flight', self.in_flight[owner], labels)
                await self.start()
                headers = {'Authorization':'Bearer '+service_token(request.app.state.auth_config,scope,owner),
                    'X-Request-ID':str(request.state.request_id),'X-Correlation-ID':str(request.state.correlation_id)}
                if getattr(request.state, 'traceparent', None): headers['traceparent']=request.state.traceparent
                for attempt in range(2):
                    retry_delay = None
                    try:
                        async with self.client.stream('GET', 'http://'+owner+':8000'+path, headers=headers) as response:
                            if response.status_code == 404:
                                await breaker.succeeded(permit)
                                raise SnapshotUnknown('source_unknown')
                            if response.status_code == 429:
                                await breaker.succeeded(permit)
                                delay = self._retry_after_seconds(response)
                                remaining = self.TOTAL_TIMEOUT_SECONDS - (self.clock() - started)
                                if attempt == 0 and delay is not None and delay <= 0.5 and delay + 0.025 < remaining:
                                    retry_delay = delay
                                else:
                                    self._increment(request, 'pulsegrid_graceful_degradations_total',
                                                    {'dependency': owner, 'outcome': 'rate_limited'})
                                    raise SnapshotUnavailable('owner_busy')
                            elif 400 <= response.status_code < 500:
                                await breaker.succeeded(permit)
                                self._increment(request, 'pulsegrid_graceful_degradations_total',
                                                {'dependency': owner, 'outcome': 'business_response'})
                                raise SnapshotUnavailable('source_rejected')
                            elif 500 <= response.status_code < 600:
                                delay = self._retry_after_seconds(response)
                                remaining = self.TOTAL_TIMEOUT_SECONDS - (self.clock() - started)
                                if response.headers.get('Retry-After') and delay is not None:
                                    if attempt == 0 and delay <= 0.5 and delay + 0.025 < remaining:
                                        retry_delay = delay
                                    else:
                                        raise _NoRetryFailure('owner_unavailable')
                                else:
                                    raise SnapshotUnavailable('owner_unavailable')
                            elif response.status_code < 200 or response.status_code >= 300:
                                raise SnapshotUnavailable('owner_unavailable')
                            elif response.status_code != 200:
                                raise SnapshotUnavailable('source_invalid')
                            else:
                                raw = bytearray()
                                async for chunk in response.aiter_bytes():
                                    raw.extend(chunk)
                                    if len(raw) > self.MAX_RESPONSE_BYTES:
                                        raise SnapshotUnavailable('source_too_large')
                                result = json.loads(raw)
                                if validate_response is not None:
                                    validate_response(result)
                                await breaker.succeeded(permit)
                                return result
                        if retry_delay is not None:
                            self._increment(request, 'pulsegrid_dependency_retry_attempts_total',
                                            {'dependency': owner, 'outcome': 'retry_after'})
                            await self.sleep(retry_delay)
                            continue
                    except SnapshotUnknown:
                        self._increment(request, 'pulsegrid_graceful_degradations_total',
                                        {'dependency': owner, 'outcome': 'source_unknown'})
                        raise
                    except _NoRetryFailure:
                        await record_failure()
                        raise SnapshotUnavailable('owner_unavailable') from None
                    except SnapshotUnavailable as exc:
                        if str(exc) in ('owner_busy', 'source_rejected'):
                            raise
                        timeout = str(exc) == 'dependency_timeout'
                        if attempt == 0:
                            self._increment(request, 'pulsegrid_dependency_retry_attempts_total',
                                            {'dependency': owner, 'outcome': 'retry'})
                            await self.sleep(0.050 + 0.025 * max(0.0, min(1.0, self.jitter())))
                            continue
                        await record_failure(timeout=timeout)
                        raise SnapshotUnavailable('owner_unavailable') from None
                    except httpx.TimeoutException:
                        if attempt == 0:
                            self._increment(request, 'pulsegrid_dependency_retry_attempts_total',
                                            {'dependency': owner, 'outcome': 'retry'})
                            self._increment(request, 'pulsegrid_dependency_timeouts_total',
                                            {'dependency': owner, 'outcome': 'attempt'})
                            await self.sleep(0.050 + 0.025 * max(0.0, min(1.0, self.jitter())))
                            continue
                        await record_failure(timeout=True)
                        raise SnapshotUnavailable('owner_unavailable') from None
                    except (httpx.HTTPError, OSError, ValueError, TypeError):
                        if attempt == 0:
                            self._increment(request, 'pulsegrid_dependency_retry_attempts_total',
                                            {'dependency': owner, 'outcome': 'retry'})
                            await self.sleep(0.050 + 0.025 * max(0.0, min(1.0, self.jitter())))
                            continue
                        await record_failure()
                        raise SnapshotUnavailable('owner_unavailable') from None
                raise SnapshotUnavailable('owner_busy')
        except asyncio.CancelledError:
            if permit is not None: await breaker.cancelled(permit)
            raise
        except SnapshotUnavailable:
            raise
        except TimeoutError:
            if permit is not None: await record_failure(timeout=True)
            self._increment(request, 'pulsegrid_graceful_degradations_total',
                            {'dependency': owner, 'outcome': 'deadline'})
            raise SnapshotUnavailable('owner_unavailable') from None
        finally:
            if in_flight:
                self.in_flight[owner] -= 1
                self._gauge(request, 'pulsegrid_bulkhead_in_flight', self.in_flight[owner], labels)
            if acquired:
                semaphore.release()

    async def episode(self, request, owner, aid, pid, prescription_id=None):
        query={'patient_id':str(pid),'limit':'100'}
        if prescription_id: query['prescription_id']=str(prescription_id)
        aggregate=None; seen=set()
        for _ in range(10):
            def validate_page(page):
                if not isinstance(page,dict) or set(page)!= {'snapshot','next_cursor'}:
                    raise SnapshotUnavailable('source_invalid')
                try:
                    validate(page['snapshot'],owner,aid,pid)
                    cursor=page['next_cursor']
                    if cursor is not None and (not isinstance(cursor,str) or not cursor or len(cursor)>2048):
                        raise SnapshotUnavailable('source_invalid')
                    paths = [('consultation','prescription','items')] if owner=='records' else (
                        [('fulfillment','items'),('fulfillment','reservations'),('fulfillment','dispensings')] if owner=='pharmacy' else [('invoice','charge_source_keys')])
                    for path in paths:
                        data=page['snapshot']
                        for key in path[:-1]:
                            data=data.get(key)
                            if data is None: break
                        if data is not None:
                            values=data.get(path[-1])
                            if not isinstance(values,list) or len(values)>100:
                                raise SnapshotUnavailable('source_invalid')
                except SnapshotUnavailable:
                    raise
                except Exception:
                    raise SnapshotUnavailable('source_invalid') from None
            page = await self.request(request,owner,'workflow:'+owner+'-read',
                '/internal/v1/appointments/'+str(aid)+'/workflow-snapshot?'+urlencode(query),
                validate_response=validate_page)
            snapshot=page['snapshot']
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
