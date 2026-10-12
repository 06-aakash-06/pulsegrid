"""Finite owner-local PostgreSQL comparison; credentials only via environment."""
import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'components/unique_id'))
from pulsegrid_unique_id import Config, Generator, PostgresWorkerStore


def percentiles(samples):
    s = sorted(samples)
    return {f'p{p}_us': s[math.ceil(p/100*len(s))-1]/1000 for p in (50,95,99)}


class Counters:
    def __init__(self): self.values = {}
    def increment(self, name, labels, value=1): self.values[name] = self.values.get(name,0)+value
    def observe(self, name, seconds, labels): pass
    def gauge(self, name, value, labels): pass


async def trial(dsn, mode, workers, clients, count, seed):
    conns = [await psycopg.AsyncConnection.connect(dsn, autocommit=True) for _ in range(clients)]
    for c in conns:
        await c.execute('CREATE TEMP TABLE entities(id bigint PRIMARY KEY)')
    generators = [Generator(Config(i), PostgresWorkerStore(dsn), observer=Counters()) for i in range(workers)] if mode == 'snowflake' else []
    samples, gen_samples, ids = [], [], set()
    collisions = rejected = 0
    try:
        for g in generators: await g.start()
        # Warmup uses the same allocator/connection shape, excluded from measured counts.
        async def operate(client, measured):
            nonlocal collisions, rejected
            conn = conns[client]
            begin = time.perf_counter_ns()
            try:
                if mode == 'snowflake': value = await generators[client % workers].next_id()
                elif mode == 'csprng': value = secrets.randbelow((1<<63)-1)+1
                else: value = (await (await conn.execute("SELECT nextval('id_benchmark_sequence')")).fetchone())[0]
                generated = time.perf_counter_ns() - begin
                await conn.execute('INSERT INTO entities VALUES (%s)', (value,))
                if measured:
                    collisions += int(value in ids)
                    ids.add(value)
                    gen_samples.append(generated)
                    samples.append(time.perf_counter_ns()-begin)
            except Exception:
                rejected += 1
                raise
        async def warm(client):
            until = time.perf_counter()+5
            while time.perf_counter()<until: await operate(client, False)
        await asyncio.gather(*(warm(i) for i in range(clients)))
        reservation_before = sum(g.store.reservations for g in generators)
        for g in generators: g.observer.values.clear()
        begin = time.perf_counter()
        async def generate(client):
            for _ in range(count//clients + int(client<count%clients)):
                await operate(client, True)
        await asyncio.gather(*(generate(i) for i in range(clients)))
        elapsed = time.perf_counter()-begin
        assert len(ids)==count and collisions==0 and rejected==0
        row = dict(attempted=count, completed=count, min_us=min(samples)/1000, max_us=max(samples)/1000, latency_samples=len(samples), mode=mode, workers=workers, clients=clients, count=count,
                   generated=count, persisted=count, collisions=collisions, rejected=rejected,
                   seconds=elapsed, ids_per_second=count/elapsed,
                   reservation_transactions=sum(g.store.reservations for g in generators)-reservation_before,
                   overflow_waits=sum(g.observer.values.get('pulsegrid_id_overflow_total',0) for g in generators),
                   restart_wait_ms=None,
                   worker_counts=json.dumps({str(i):g.observer.values.get('pulsegrid_id_generated_total',0) for i,g in enumerate(generators)},sort_keys=True))
        row.update(percentiles(samples))
        row.update({'generation_'+k:v for k,v in percentiles(gen_samples).items()})
        return row, samples, gen_samples
    finally:
        for g in generators: await g.close()
        for c in conns: await c.close()


async def main(args):
    dsn = os.environ['ID_BENCHMARK_DSN']
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    raw = Path('experiments/phase4/unique_id/artifacts') / output.name
    raw.mkdir(parents=True, exist_ok=True)
    workers, clients, count = {'low':(1,1,100000),'medium':(4,8,400000),'high':(16,32,1000000)}[args.level]
    started = datetime.now(timezone.utc).isoformat()
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as c:
        version = (await (await c.execute('SHOW server_version')).fetchone())[0]
        await c.execute('CREATE SEQUENCE IF NOT EXISTS id_benchmark_sequence')
    rows, hashes = [], {}
    all_samples = {}
    for repeat in ([args.trial-1] if args.trial else range(3)):
        modes = ['csprng','sequence','snowflake']
        if repeat%2: modes.reverse()
        for mode in modes:
            row, samples, generation = await trial(dsn,mode,workers,clients,count,args.seed+repeat)
            row.update(repeat=repeat+1, seed=args.seed+repeat, level=args.level)
            rows.append(row)
            p = raw / f'{mode}-{repeat+1}.json'
            p.write_text(json.dumps({'pipeline_ns':samples,'generation_ns':generation},separators=(',',':')))
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            all_samples[mode] = sorted(samples)
            (output/'partial.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(json.dumps(row), flush=True)
    with (output/'summary.csv').open('w') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    manifest = dict(started=started, ended=datetime.now(timezone.utc).isoformat(),
                    os=platform.platform(), machine=platform.machine(), python=sys.version,
                    cpu_count=os.cpu_count(), postgres=version, psycopg=psycopg.__version__,
                    base='45273ea7fd1ea53e335942b6c38f2d81d38856ee',
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    component_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path('components/unique_id/pulsegrid_unique_id')).glob('*.py')},
                    hardware=subprocess.check_output(['sysctl','-n','hw.model','hw.memsize','machdep.cpu.brand_string'],text=True).strip(),
                    resource_limits='no explicit CPU/memory cap; max run 600 seconds; no connection pool; max workers+clients dedicated connections',
                    command=f'python experiments/phase4/unique_id/run.py --seed {args.seed} --level {args.level} --output {args.output}' + (f' --trial {args.trial}' if args.trial else ''),
                    samples_sha256=hashes, topology='one Python asyncio process, loopback dedicated disposable PostgreSQL 14, one dedicated store session per worker; one insert connection per client',
                    config=dict(epoch_ms=1767225600000, bits=[41,10,12],span_ms=100,wait_ms=2000),
                    timer=time.get_clock_info('perf_counter').resolution, seed_role='repeat label; ID outputs intentionally use real clock/CSPRNG',
                    limitations=['PostgreSQL 14 locally available, PostgreSQL 16 deployment validation pending','temporary per-client PK tables plus whole-trial global set; no existing tables changed','not hospital endpoint integration','sequence baseline technical nextval equivalent, not Records endpoint','single process concurrency; multiprocess correctness separately tested'])
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    report = '# Measured unique ID comparison\n\nMeasured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.\n\n'
    for mode in ['csprng','sequence','snowflake']:
        r = [x for x in rows if x['mode']==mode]
        report += f"- {mode}: IDs/s {[round(x['ids_per_second']) for x in r]}; pipeline p95 us {[round(x['p95_us'],1) for x in r]}; observed collisions 0 across {count*len(r)} measured IDs.\n"
    report += '\nNo global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.\n'
    (output/'report.md').write_text(report)
    colors = dict(csprng='#2563eb',sequence='#9333ea',snowflake='#dc2626')
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="700" height="360"><rect width="700" height="360" fill="white"/><text x="20" y="25">Pipeline latency CDF, final trial (log10 microseconds)</text>']
    for j,(mode,s) in enumerate(all_samples.items()):
        points=[]
        for q in range(1,101):
            us=s[math.ceil(q/100*len(s))-1]/1000
            points.append(f'{40+min(600,max(0,math.log10(max(us,1))*120)):.1f},{320-q*2.6:.1f}')
        lines.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[mode]}"/><text x="480" y="{40+j*20}" fill="{colors[mode]}">{mode}</text>')
    lines.append('<text x="40" y="345">1 us</text><text x="270" y="345">100 us</text><text x="500" y="345">10,000 us</text></svg>')
    (output/'latency.svg').write_text(''.join(lines))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--seed',type=int,default=404); p.add_argument('--trial',type=int,choices=[1,2,3]); p.add_argument('--level',choices=['low','medium','high'],required=True); p.add_argument('--output',required=True)
    async def bounded():
        async with asyncio.timeout(600):
            await main(p.parse_args())
    asyncio.run(bounded())
