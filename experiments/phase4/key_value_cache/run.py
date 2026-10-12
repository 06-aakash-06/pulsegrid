#!/usr/bin/env python3
"""Real-storage adapter benchmark, deliberately unmounted from owner HTTP APIs."""
import argparse
import asyncio
import csv
import contextvars
import hashlib
import json
import math
import os
import platform
import random
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from pulsegrid_key_value_cache import Cache, redis_client
from doctor_service.features.directory_cache import DirectoryFilters, cache_projection, load_projection, read_revision
from fixtures import storage, seed


class Placement:
    epoch = 1
    def locate(self, key):
        # Harness only. Coordinator must inject the reviewed Agent 2 ring.
        return ('cache_a', 'cache_b')[int.from_bytes(hashlib.sha256(key).digest(), 'big') % 2]


lookup_outcome = contextvars.ContextVar('lookup_outcome', default='uncached')


class Metrics:
    def __init__(self): self.counts = Counter(); self.timings = {}
    def increment(self, name, labels, value=1):
        self.counts[(name, labels.get('outcome', labels.get('kind', 'all')))] += value
        if name == 'pulsegrid_cache_requests_total': lookup_outcome.set(labels['outcome'])
    def observe(self, name, seconds, labels): self.timings.setdefault(name, []).append(seconds * 1000)
    def gauge(self, *args): pass


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values)*p)-1)] if values else None


def utc(): return datetime.now(timezone.utc).isoformat()


async def benchmark(args, engine, ports, processes, raw_path):
    sessions = async_sessionmaker(engine)
    rows, clients, reuse = {'low':(1000,1,.5),'medium':(10000,8,.8),'high':(50000,32,.95)}[args.level]
    await seed(engine, rows)
    fields = []
    raw = open(raw_path, 'w')
    queries = [DirectoryFilters('synthetic', 'patient', specialty_id=str(s), query='synthetic doctor', limit=20) for s in range(1,11)]
    input_hash = hashlib.sha256(json.dumps([dict(specialty=f.specialty_id,query=f.query,limit=f.limit) for f in queries],sort_keys=True).encode()).hexdigest()
    try:
        for trial in range(3):
            trial_seed = args.seed + trial
            scenarios = ['uncached','cold','warm','invalidation','redis_failure']
            if trial % 2: scenarios.reverse()
            for scenario in scenarios:
                metrics = Metrics()
                caches = [Cache(Placement(), {'cache_a':redis_client(f'redis://127.0.0.1:{ports[0]}'), 'cache_b':redis_client(f'redis://127.0.0.1:{ports[1]}')}, observer=metrics) for _ in range(2)]
                samples, errors, unavailable_samples, db_queries = [], [], [], 0
                mutation_task = None; failure_task = None
                # FLUSHDB is permitted only on these freshly created disposable servers.
                for client in caches[0].clients.values(): await client.flushdb()
                async def one(f, cache):
                    nonlocal db_queries
                    async def loader():
                        nonlocal db_queries
                        async with sessions() as s:
                            db_queries += 1
                            return await load_projection(s,f)
                    if scenario == 'uncached':
                        revision,payload = await loader()
                        return json.loads(payload)
                    async with sessions() as s:
                        db_queries += 1
                        revision = await read_revision(s)
                    return await cache_projection(cache,revision,f,loader)
                async def workers(duration, record):
                    deadline = time.perf_counter()+duration
                    async def worker(index):
                        rng = random.Random(trial_seed*100+index)
                        while time.perf_counter() < deadline:
                            f = queries[0] if rng.random() < reuse else rng.choice(queries[1:])
                            if scenario == 'cold':
                                async with sessions() as s: rev = await read_revision(s)
                                await caches[index%2].invalidate(f.key(rev))
                            lookup_outcome.set('uncached')
                            start = time.perf_counter_ns()
                            try:
                                result = await one(f,caches[index%2])
                                # Check allowed shape/specialty and bounded pagination every operation.
                                assert len(result['items']) == 20
                                assert all(any(s['id']==f.specialty_id for s in item['specialties']) for item in result['items'])
                                elapsed = (time.perf_counter_ns()-start)/1e6
                                if record:
                                    samples.append(elapsed)
                                    if lookup_outcome.get() == 'unavailable': unavailable_samples.append(elapsed)
                                    raw.write(json.dumps(dict(trial=trial,seed=trial_seed,scenario=scenario,ms=elapsed,outcome=lookup_outcome.get()))+'\n')
                            except Exception as exc:
                                elapsed = (time.perf_counter_ns()-start)/1e6
                                if record: errors.append(elapsed)
                                raise RuntimeError(f'{scenario} failed ({type(exc).__name__})') from exc
                    await asyncio.gather(*(worker(i) for i in range(clients)))
                async def mutate():
                    while True:
                        await asyncio.sleep(.5)
                        async with engine.begin() as conn:
                            await conn.execute(text("UPDATE doctors SET display_name=CASE WHEN display_name='Synthetic doctor 000001' THEN 'Synthetic doctor changed' ELSE 'Synthetic doctor 000001' END WHERE id=1"))
                            await conn.execute(text('UPDATE directory_revision SET revision=revision+1'))
                async def outage():
                    # Only our owned disposable processes; restore even on cancellation.
                    await asyncio.sleep(min(1,args.duration/4))
                    try:
                        for process in processes: os.kill(process.pid,signal.SIGSTOP)
                        await asyncio.sleep(2)
                    finally:
                        for process in processes: os.kill(process.pid,signal.SIGCONT)
                try:
                    await workers(args.warmup,False)
                    if scenario == 'cold':
                        for client in caches[0].clients.values(): await client.flushdb()
                    metrics.counts.clear(); metrics.timings.clear(); db_queries=0
                    if scenario == 'invalidation': mutation_task = asyncio.create_task(mutate())
                    if scenario == 'redis_failure': failure_task = asyncio.create_task(outage())
                    start=time.perf_counter()
                    await workers(args.duration,True)
                    wall=time.perf_counter()-start
                    hits=metrics.counts[('pulsegrid_cache_requests_total','hit')]
                    misses=metrics.counts[('pulsegrid_cache_requests_total','miss')]
                    unavailable=metrics.counts[('pulsegrid_cache_requests_total','unavailable')]
                    fields.append(dict(level=args.level,trial=trial+1,seed=trial_seed,scenario=scenario,rows=rows,clients=clients,
                                       attempted=len(samples)+len(errors),completed=len(samples),errors=len(errors),wall_seconds=wall,
                                       mean_ms=sum(samples)/len(samples),p50_ms=percentile(samples,.5),p95_ms=percentile(samples,.95),p99_ms=percentile(samples,.99),min_ms=min(samples),max_ms=max(samples),
                                       throughput=len(samples)/wall,hits=hits,misses=misses,unavailable=unavailable,bypasses=metrics.counts[('pulsegrid_cache_requests_total','bypass')],
                                       hit_ratio=hits/(hits+misses) if hits+misses else None,db_queries=db_queries,
                                       unavailable_p95_ms=percentile(unavailable_samples,.95),unavailable_p99_ms=percentile(unavailable_samples,.99),
                                       lookup_p95_ms=percentile(metrics.timings.get('pulsegrid_cache_lookup_seconds',[]),.95),
                                       load_p95_ms=percentile(metrics.timings.get('pulsegrid_cache_load_seconds',[]),.95),
                                       success_ratio=len(samples)/(len(samples)+len(errors))))
                    print(json.dumps(fields[-1]),flush=True)
                finally:
                    for task in (mutation_task,failure_task):
                        if task:
                            task.cancel()
                            try: await task
                            except asyncio.CancelledError: pass
                    if scenario == 'redis_failure':
                        for cache in caches:
                            for client in cache.clients.values(): assert await client.ping()
                    for cache in caches: await cache.close()
    finally: raw.close()
    return fields,input_hash


async def main(args):
    out=Path(args.output); out.mkdir(parents=True,exist_ok=False)
    raw_dir=Path('artifacts/phase4/key_value_cache')/out.name; raw_dir.mkdir(parents=True,exist_ok=False)
    raw_path=raw_dir/'samples.jsonl'; started=utc()
    with storage() as (dsn,ports,processes):
        engine=create_async_engine(dsn,pool_size=32,max_overflow=0,pool_timeout=1,connect_args={'options':'-c statement_timeout=2000'})
        try:
            results,input_hash=await benchmark(args,engine,ports,processes,raw_path)
            async with engine.connect() as conn: pg_version=(await conn.execute(text('SELECT version()'))).scalar_one()
        finally: await engine.dispose()
    with open(out/'summary.csv','w') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0])); writer.writeheader(); writer.writerows(results)
    manifest=dict(started_utc=started,ended_utc=utc(),base_commit='45273ea7fd1ea53e335942b6c38f2d81d38856ee',
                  source_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),source_dirty=True,
                  source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('fixtures.py'),Path('components/key_value_cache/src/pulsegrid_key_value_cache/__init__.py'),Path('services/doctor/doctor_service/features/directory_cache/__init__.py')]},
                  python=sys.version,platform=platform.platform(),cpu=platform.processor(),cpu_count=os.cpu_count(),memory_bytes=int(subprocess.check_output(['sysctl','-n','hw.memsize'],text=True)),
                  postgres=pg_version,redis=subprocess.check_output(['redis-server','--version'],text=True).strip(),
                  dependencies=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
                  topology='one adapter process, two replica cache objects, two independent loopback Redis nodes; SHA256 modulo HARNESS, no Agent 2 ring',pool_size=32,max_overflow=0,
                  level=args.level,seed=args.seed,repeat_seeds=[args.seed+i for i in range(3)],warmup_seconds=args.warmup,measurement_seconds=args.duration,
                  ttl_ms=30000,command_timeout_ms=50,connect_timeout_ms=50,outer_timeout_ms=100,
                  timer=time.get_clock_info('perf_counter').__dict__,dataset_generation='fixtures.seed(engine, level_rows); ten specialties; ordered synthetic active doctors',
                  dataset_hash=hashlib.sha256(b''.join(f'{i}|Synthetic doctor {i:06d}|true|{1+i%10}\n'.encode() for i in range(1,{'low':1000,'medium':10000,'high':50000}[args.level]+1))).hexdigest(),query_hash=input_hash,
                  raw_path=str(raw_path),raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),raw_bytes=raw_path.stat().st_size,
                  request_count=sum(r['completed'] for r in results),command=' '.join(sys.argv),
                  limitations=['Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.','Test-only DDL, no production migration.','Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.','Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.','Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.','No real consistent ring or HA claim.','No OS/container resource limits imposed.'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,default=str)+'\n')
    report=['# Measured key-value cache adapter benchmark','',f"Level {args.level}; 3 trials with seeds {args.seed}..{args.seed+2}; {args.warmup}s warmup and {args.duration}s measurement per scenario.",'','| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |','|---|---:|---:|---:|---:|---:|']
    aggregated=[]
    for scenario in ['uncached','cold','warm','invalidation','redis_failure']:
        group=[r for r in results if r['scenario']==scenario]
        mean=lambda field: sum(r[field] for r in group)/3
        hits=sum(r['hits'] for r in group); misses=sum(r['misses'] for r in group)
        ratio=hits/(hits+misses) if hits+misses else None
        report.append(f"| {scenario} | {mean('mean_ms'):.3f} | {mean('p95_ms'):.3f} | {mean('throughput'):.1f} | {ratio if ratio is not None else 'n/a'} | {sum(r['db_queries'] for r in group)/sum(r['completed'] for r in group):.3f} |")
        aggregated.append((scenario,mean('mean_ms'),mean('p95_ms')))
    report+=['','p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.','']+manifest['limitations']
    (out/'report.md').write_text('\n'.join(report)+'\n')
    scale=450/max(v[2] for v in aggregated)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="850" height="260">','<rect width="100%" height="100%" fill="white"/>','<text x="10" y="20">Mean (blue) and p95 (orange) adapter latency, milliseconds</text>']
    for i,(label,mean,p95) in enumerate(aggregated):
        y=40+i*40
        svg += [f'<text x="10" y="{y+15}">{label}</text>',f'<rect x="160" y="{y}" width="{mean*scale}" height="12" fill="#2563eb"/>',f'<rect x="160" y="{y+14}" width="{p95*scale}" height="12" fill="#ea580c"/>',f'<text x="630" y="{y+20}">{mean:.3f} / {p95:.3f} ms</text>']
    (out/'latency.svg').write_text('\n'.join(svg+['</svg>']))
    print(f'completed {out}; owned storage cleanup passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--seed',type=int,default=404); parser.add_argument('--level',choices=['low','medium','high'],required=True); parser.add_argument('--output',required=True); parser.add_argument('--warmup',type=float,default=5); parser.add_argument('--duration',type=float,default=30)
    args=parser.parse_args()
    if not 3 <= args.duration <= 30 or not 0 <= args.warmup <= 5: parser.error('duration 3..30, warmup 0..5')
    asyncio.run(main(args))
