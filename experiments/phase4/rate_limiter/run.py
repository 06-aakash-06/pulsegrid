#!/usr/bin/env python3
"""Measured multiprocess baseline/Redis decisions; owned disposable resources only."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from pulsegrid_rate_limiter import IdentityDeriver, LimiterConfig, RateLimiter, build_buckets
from pulsegrid_rate_limiter.local import LocalBuckets
from pulsegrid_rate_limiter.limiter import KeyedBucket
from resources import DisposableRedis
from fixtures import PARTITIONS, workload

ROOT=Path(__file__).resolve().parents[3]
LEVELS={'low':(1,8,50),'medium':(2,32,200),'high':(4,128,800)}
SECRET=b'fixed-synthetic-benchmark-only-key-404'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def quantile(samples,p):
    return sorted(samples)[max(0,math.ceil(p*len(samples))-1)] if samples else None

def decision_buckets(identity, partition, trial, derive):
    # Repeat namespace lives in bounded policy family, HMAC hides identities.
    route=PARTITIONS[partition]
    route=type(route)(route.owner,route.policy,route.family+f'_trial{trial}')
    identities={'source':derive.digest('source',f'synthetic-source-{identity}'),
        'principal':derive.principal(str(identity+1)),
        'account':derive.digest('account',f'normalized-fixture-{identity}')}
    return build_buckets(route,identities,derive)

async def execute_worker(args):
    backend,index,processes,clients,rate,seed,trial,url,start,warmup,duration=args
    derive=IdentityDeriver(SECRET)
    limiter=RateLimiter(LimiterConfig(enabled=True,redis_endpoint=url,hmac_secret=SECRET,
                                     max_replicas=4,max_connections=clients))
    local=LocalBuckets(1,10000)
    rows=[]
    cache={}
    async def client_loop(client_id):
        period=clients/rate
        steps=math.ceil((warmup+duration)/period)
        trace=workload(seed+client_id*100003,steps)
        for i,(identity,partition) in enumerate(trace):
            due=start+i*period
            await asyncio.sleep(max(0,due-time.perf_counter()))
            # Closed-loop client never has two in-flight decisions.
            if time.perf_counter() >= start+warmup+duration: break
            key=(identity,partition)
            if key not in cache: cache[key]=decision_buckets(identity,partition,trial,derive)
            buckets=cache[key]
            before=time.perf_counter_ns()
            if backend=='redis': result=await limiter.admit(buckets)
            else: result=local.decide([KeyedBucket(limiter.key(b),b.spec) for b in buckets])
            after=time.perf_counter_ns()
            if before/1e9 >= start+warmup:
                rows.append({'at_s':before/1e9-start-warmup,'latency_ms':(after-before)/1e6,
                    'queue_delay_ms':max(0,(before/1e9-due)*1000),'outcome':result.reason,
                    'backend':result.mode if backend=='redis' else 'baseline',
                    'identity_index':identity,'partition':partition,'process':index})
    try:
        await asyncio.gather(*(client_loop(c) for c in range(index,clients,processes)))
        return rows
    finally: await limiter.close()

def worker(args,output):
    try: output.put(('ok',asyncio.run(execute_worker(args))))
    except BaseException as exc: output.put(('error',type(exc).__name__+': '+str(exc)))

def trial(backend,processes,clients,rate,seed,repeat,url,warmup,duration):
    ctx=mp.get_context('spawn')
    output=ctx.Queue()
    # Shared monotonic deadline leaves spawn/import startup outside warmup.
    start=time.perf_counter()+2
    workers=[ctx.Process(target=worker,args=((backend,i,processes,clients,rate,seed,
        repeat,url,start,warmup,duration),output)) for i in range(processes)]
    rows=[]
    try:
        for p in workers: p.start()
        for _ in workers:
            status,value=output.get(timeout=warmup+duration+15)
            if status!='ok': raise RuntimeError(value)
            rows.extend(value)
        for p in workers:
            p.join(5)
            if p.exitcode != 0: raise RuntimeError('Decision process failed')
        return rows
    finally:
        for p in workers:
            if p.is_alive(): p.terminate(); p.join(5)
        output.close()

def summarise(rows,level,backend,repeat,seed,processes,clients,rate,duration):
    accepted=sum(r['outcome']=='accepted' for r in rows)
    limited=sum(r['outcome']=='limited' for r in rows)
    unavailable=sum(r['outcome']=='unavailable' for r in rows)
    samples=[r['latency_ms'] for r in rows]
    result=dict(level=level,backend=backend,trial=repeat,seed=seed,processes=processes,clients=clients,
        target_rps=rate,attempted=len(rows),completed=len(rows),accepted=accepted,limited=limited,
        unavailable=unavailable,rejection_percent=100*limited/(accepted+limited) if accepted+limited else None,
        fallback_percent=100*sum(r['backend']=='local' for r in rows)/len(rows) if rows else None,
        attempted_throughput=len(rows)/duration,throughput=len(rows)/duration,
        unmet_arrivals=max(0,round(rate*duration)-len(rows)),admission_p50_ms=quantile(samples,.5),
        admission_p95_ms=quantile(samples,.95),admission_p99_ms=quantile(samples,.99),
        admission_min_ms=min(samples) if samples else None,admission_max_ms=max(samples) if samples else None,
        sample_count=len(samples),queue_p95_ms=quantile([r['queue_delay_ms'] for r in rows],.95))
    for outcome in ('accepted','limited','unavailable'):
        selected=[r['latency_ms'] for r in rows if r['outcome']==outcome]
        result[outcome+'_sample_count']=len(selected)
        for p,label in ((.5,'p50'),(.95,'p95'),(.99,'p99')):
            result[outcome+'_'+label+'_ms']=quantile(selected,p)
    return result

async def burst(url,processes,baseline):
    derive=IdentityDeriver(SECRET)
    ls=[RateLimiter(LimiterConfig(enabled=True,redis_endpoint=url,hmac_secret=SECRET)) for _ in range(processes)]
    locals_=[LocalBuckets(1,10000) for _ in ls]
    from pulsegrid_rate_limiter import RoutePolicy
    route=RoutePolicy('doctor','directory_search','burst'+('baseline' if baseline else 'redis'))
    buckets=build_buckets(route,{'principal':derive.principal('1')},derive)
    zero=time.perf_counter()
    samples=[]
    await ls[0].redis.script_load(__import__('pulsegrid_rate_limiter.limiter',fromlist=['SCRIPT']).SCRIPT)
    await asyncio.gather(*(l.redis.ping() for l in ls))
    semaphore=asyncio.Semaphore(16)
    async def once(i):
        scheduled=zero
        async with semaphore:
            before=time.perf_counter()
            if baseline: result=locals_[i%processes].decide([KeyedBucket(ls[i%processes].key(b),b.spec) for b in buckets])
            else: result=await ls[i%processes].admit(buckets)
            elapsed=time.perf_counter()-zero
            samples.append({'at_s':elapsed,'accepted':int(result.allowed),
                'queue_delay_ms':(before-scheduled)*1000,'latency_ms':(time.perf_counter()-before)*1000})
    try:
        await asyncio.gather(*(once(i) for i in range(160)))
    finally: await asyncio.gather(*(l.close() for l in ls))
    accepted=sum(r['accepted'] for r in samples)
    theoretical=60+10*(time.perf_counter()-zero)
    if not baseline and accepted > math.floor(theoretical): raise RuntimeError('Burst exceeded shared quota')
    return {'backend':'baseline' if baseline else 'redis','attempted':160,'accepted':accepted,
        'theoretical_shared_bound':theoretical,'excess_shared_admissions':max(0,accepted-math.floor(theoretical)),
        'p95_ms':quantile([r['latency_ms'] for r in samples],.95),
        'queue_p95_ms':quantile([r['queue_delay_ms'] for r in samples],.95),'samples':samples}

def svg_cdf(path,raw):
    colors=['#1565c0','#c62828']
    pieces=['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="440" viewBox="0 0 800 440">',
        '<rect width="800" height="440" fill="white"/><text x="40" y="25">Admission latency CDF (log1p milliseconds)</text>']
    maximum=max(r['latency_ms'] for rows in raw.values() for r in rows)
    for (backend,rows),color in zip(raw.items(),colors):
        values=sorted(r['latency_ms'] for r in rows)
        points=[]
        for i in range(0,len(values),max(1,len(values)//300)):
            x=60+680*math.log1p(values[i])/math.log1p(maximum)
            y=370-300*(i+1)/len(values)
            points.append(f'{x:.2f},{y:.2f}')
        pieces += [f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}"/>',
            f'<text x="{60+len(pieces)*30}" y="410" fill="{color}">{backend}</text>']
    pieces += [f'<text x="60" y="390">0 ms</text><text x="650" y="390">{maximum:.3f} ms</text>',
        '<text x="15" y="72">100%</text><text x="20" y="370">0%</text></svg>']
    path.write_text('\n'.join(pieces))

def bars(path,summary):
    pieces=['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="360">',
        '<rect width="800" height="360" fill="white"/><text x="20" y="25">Measured outcomes (accepted / limited / unavailable)</text>']
    for i,row in enumerate(summary):
        y=55+i*44; x=200
        pieces.append(f'<text x="15" y="{y+15}">{row["backend"]} seed {row["seed"]}</text>')
        for outcome,color in [('accepted','#2e7d32'),('limited','#ef6c00'),('unavailable','#b71c1c')]:
            width=550*row[outcome]/row['completed'] if row['completed'] else 0
            pieces.append(f'<rect x="{x}" y="{y}" width="{width}" height="25" fill="{color}"/>')
            x+=width
    pieces.append('</svg>');path.write_text('\n'.join(pieces))

def quota_plot(path,curves):
    maximum=max(r['at_s'] for r in curves)
    ymax=max(max(r['cumulative_debit'],r['theoretical_shared_tokens']) for r in curves)
    pieces=['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="430">',
        '<rect width="800" height="430" fill="white"/><text x="30" y="25">Burst cumulative debit vs shared refill envelope</text>']
    for name,field,color in [('baseline','cumulative_debit','#c62828'),('redis','cumulative_debit','#1565c0'),
                             ('redis','theoretical_shared_tokens','#2e7d32')]:
        selected=sorted((r for r in curves if r['backend']==name),key=lambda r:r['at_s'])
        points=' '.join(f"{60+680*r['at_s']/maximum:.2f},{370-300*r[field]/ymax:.2f}" for r in selected)
        pieces.append(f'<polyline points="{points}" fill="none" stroke="{color}"/>')
    pieces += [f'<text x="60" y="400">0 seconds</text><text x="650" y="400">{maximum:.3f} seconds</text>',
        f'<text x="5" y="70">{ymax:.0f}</text><text x="20" y="370">0</text>',
        '<text x="60" y="420">Red baseline / blue Redis / green shared token envelope</text></svg>']
    path.write_text('\n'.join(pieces))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seed',type=int,default=404)
    parser.add_argument('--level',choices=LEVELS,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--warmup',type=float,default=5)
    parser.add_argument('--duration',type=float,default=30)
    args=parser.parse_args()
    output=args.output.resolve()
    owned=Path(__file__).resolve().parent/'results'
    if not output.is_relative_to(owned): raise SystemExit('Output must be in owned results prefix')
    if output.exists(): raise SystemExit('Refusing to overwrite an existing run')
    if args.duration <= 0 or args.warmup < 0 or 6*(args.duration+args.warmup+2)>540:
        raise SystemExit('Invalid duration or ten-minute bound exceeded')
    output.mkdir(parents=True)
    artifact=ROOT/'artifacts/phase4/rate_limiter'/output.name
    artifact.mkdir(parents=True,exist_ok=False)
    started=utc();processes,clients,rate=LEVELS[args.level]
    summary=[];raw={'baseline':[],'redis':[]};hashes={}
    with DisposableRedis() as server:
        version=server.version
        for repeat in range(3):
            seed=args.seed+repeat
            for backend in (('baseline','redis') if repeat%2==0 else ('redis','baseline')):
                rows=trial(backend,processes,clients,rate,seed,repeat,server.url,args.warmup,args.duration)
                path=artifact/f'{backend}-{seed}.json'
                path.write_text(json.dumps(rows,separators=(',',':')))
                hashes[path.name]=sha(path)
                raw[backend].extend(rows)
                result=summarise(rows,args.level,backend,repeat,seed,processes,clients,rate,args.duration)
                summary.append(result)
                print(json.dumps(result),flush=True)
        bursts=[asyncio.run(burst(server.url,processes,baseline)) for baseline in (True,False)]
    # Exiting context must successfully clean the disposable Redis before success output.
    with (output/'summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]),lineterminator="\n");writer.writeheader();writer.writerows(summary)
    curves=[]
    for b in bursts:
        total=0
        for sample in sorted(b['samples'],key=lambda r:r['at_s']):
            total+=sample['accepted']
            curves.append({'backend':b['backend'],'at_s':sample['at_s'],'cumulative_debit':total,
                           'theoretical_shared_tokens':60+10*sample['at_s'],
                           'queue_delay_ms':sample['queue_delay_ms']})
    with (output/'quota_curve.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(curves[0]),lineterminator="\n");writer.writeheader();writer.writerows(curves)
    (output/'burst.json').write_text(json.dumps([{k:v for k,v in b.items() if k!='samples'} for b in bursts],indent=2))
    svg_cdf(output/'latency.svg',raw);bars(output/'outcomes.svg',summary)
    quota_plot(output/'quota_curve.svg',curves)
    # Baseline excess is a correctness difference, never a speed success.
    pairs=[]
    for repeat in range(3):
        a=next(r for r in summary if r['trial']==repeat and r['backend']=='baseline')
        b=next(r for r in summary if r['trial']==repeat and r['backend']=='redis')
        pairs.append({'seed':a['seed'],'p95_difference_ms':b['admission_p95_ms']-a['admission_p95_ms'],
            'baseline_over_redis_p95':a['admission_p95_ms']/b['admission_p95_ms'],
            'accepted_difference':a['accepted']-b['accepted']})
    source_paths=sorted((ROOT/'components/rate_limiter/src').rglob('*'))
    source_hash=hashlib.sha256(b''.join(p.read_bytes() for p in source_paths if p.is_file() and '__pycache__' not in str(p))).hexdigest()
    dataset=artifact/'input.json'
    dataset.write_text(json.dumps(workload(args.seed,10000)))
    def command(*values): return subprocess.check_output(values,text=True).strip()
    manifest={'start_utc':started,'end_utc':utc(),'command':sys.argv,'level':args.level,
        'seeds':[args.seed+i for i in range(3)],'warmup_seconds':args.warmup,'measurement_seconds':args.duration,
        'full_protocol':args.warmup==5 and args.duration==30,'processes':processes,'clients':clients,
        'target_rps':rate,'hardware':platform.platform(),'machine':platform.machine(),
        'cpu':command('sysctl','-n','machdep.cpu.brand_string') if sys.platform=='darwin' else platform.processor(),
        'cpu_count':os.cpu_count(),'memory_bytes':command('sysctl','-n','hw.memsize') if sys.platform=='darwin' else None,
        'python':platform.python_version(),'redis':version,'postgresql':'not used',
        'redis_topology':'one owned standalone Redis; loopback Docker VM' if server.image else 'one owned standalone Redis; host loopback',
        'redis_resource_limits':'64 MiB noeviction; Docker 128 MiB and one CPU' if server.image else '64 MiB noeviction; host process CPU uncapped',
        'pool_size_per_process':clients,'max_replicas':4,'identity_count':100,'hot_identity_share':.5,
        'policies':{r.policy:dict(__import__('pulsegrid_rate_limiter').BUDGETS[r.policy]) for r in PARTITIONS},
        'component_commit':command('git','rev-parse','HEAD'),'baseline_commit':command('git','rev-parse','HEAD'),
        'source_tree_sha256':source_hash,'dependency_lock_sha256':sha(ROOT/'components/rate_limiter/requirements-test.lock'),
        'fixture_generator_sha256':sha(Path(__file__).with_name('fixtures.py')),
        'runner_sha256':sha(Path(__file__)),'dataset_sha256':sha(dataset),'raw_output_sha256':hashes,
        'raw_sample_count':sum(len(r) for r in raw.values()),'timer_resolution_s':time.get_clock_info('perf_counter').resolution,
        'nearest_rank':'ceil(p*n)-1','pair_comparisons':pairs,'cleanup':'passed',
        'limitations':['component decisions, no HTTP/auth/business DB timing',
            'closed-loop decisions paced at target rate; queue delay records scheduler lateness',
            'burst uses independent limiter objects, service trials use actual decision processes',
            'CPU-only baseline and network Redis latency reported separately by backend',
            'dataset hash is seed404 reference trace; worker traces generated with seed+client_id*100003']}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'report.md').write_text(f'# {args.level} component decisions\n\nMeasured three trials, seeds {args.seed}–{args.seed+2}, '
        f'{processes} processes and {clients} clients; {args.warmup}s warmup and {args.duration}s measurement each backend/trial. '
        'See summary.csv for every outcome and latency including rejections. Baseline has no distributed quota guarantee. '
        'Redis adds network latency; no throughput superiority or production capacity claim. '
        'Rejection denominator accepted+limited; unavailable separate. Throughput completed/measurement_seconds. '
        'Latency percentiles use nearest rank. Queue delay is separate.\n\n'
        + '\n'.join(f'- {r["backend"]} seed {r["seed"]}: {r["completed"]} completed, {r["accepted"]} accepted, '
            f'{r["limited"]} limited, {r["unavailable"]} unavailable; {r["throughput"]:.2f}/s; '
            f'p95 {r["admission_p95_ms"]:.3f} ms.' for r in summary)
        +'\n\nBurst: '+json.dumps([{k:v for k,v in b.items() if k!='samples'} for b in bursts])
        +'\n\nDisposable Redis cleanup passed. Hospital mounting/gateway/browser acceptance remains coordinator work.\n')

if __name__=='__main__': main()
