#!/usr/bin/env python3
"""Finite CPU-only experiment, standard library only; never accesses Redis."""
import argparse
from bisect import bisect_left
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "components/consistent_hashing"))
from pulsegrid_consistent_hashing import HashRing, RingSnapshot  # noqa: E402


class Modulo:
    def __init__(self, nodes):
        self.nodes = tuple(sorted(nodes))

    def locate(self, key):
        return self.nodes[int.from_bytes(hashlib.sha256(b"pg-ring-key-v1\0" + key).digest(), "big") % len(self.nodes)]


def keys_for(seed, count):
    rng = random.Random(seed)
    # Unique logical keys, random reproducible suffixes, no hospital identities.
    return [f"synthetic:{i}:{rng.getrandbits(64):016x}".encode() for i in range(count)]


def percentile(samples, p):
    return samples[math.ceil(p * len(samples)) - 1]


def csv_write(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bars(path, title, rows):
    width, height = 900, 65 + 23 * len(rows)
    peak = max(v for _, v in rows) or 1
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                '<rect width="100%" height="100%" fill="white"/>',
                f'<text x="15" y="25" font-family="sans-serif" font-size="16">{title}</text>']
    for i, (label, value) in enumerate(rows):
        y = 47 + i * 23
        elements += [f'<text x="15" y="{y+12}" font-family="sans-serif" font-size="11">{label}</text>',
                     f'<rect x="330" y="{y}" width="{value/peak*440:.2f}" height="16" fill="#267b99"/>',
                     f'<text x="780" y="{y+12}" font-family="sans-serif" font-size="11">{value:.3f}</text>']
    path.write_text("\n".join(elements + ["</svg>"]) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=404)
    parser.add_argument("--level", choices=("low", "medium", "high"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    owned = (ROOT / "experiments/phase4/consistent_hashing").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(owned / "results"):
        parser.error("output must be within experiments/phase4/consistent_hashing/results")
    output.mkdir(parents=True, exist_ok=False)
    raw = owned / "artifacts" / output.name
    raw.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    wall_start = time.perf_counter()
    count = {"low": 10000, "medium": 100000, "high": 1000000}[args.level]
    summary, distribution, movement, builds, raw_files = [], [], [], [], []
    for trial in range(3):
        seed = args.seed + trial
        keys = keys_for(seed, count)
        input_file = raw / f"keys-{seed}.txt"
        input_file.write_bytes(b"\n".join(keys) + b"\n")
        raw_files.append(input_file)
        # Zipf exponent 1.1, finite ranks; placement and access load distinct.
        cumulative = []
        running = 0.0
        for rank in range(1, count + 1):
            running += rank ** -1.1
            cumulative.append(running)
        rng = random.Random(seed)
        accesses = Counter(bisect_left(cumulative, rng.random() * running) for _ in range(count))
        trace_file = raw / f"zipf-{seed}.json"
        trace_file.write_text(json.dumps(sorted(accesses.items()), separators=(",", ":")))
        raw_files.append(trace_file)
        algorithms = [("modulo", 0), ("ring", 32), ("ring", 128), ("ring", 512)]
        if trial % 2:
            algorithms.reverse()
        for algorithm, vnodes in algorithms:
            placements = {}
            ring3 = None
            for size in (1, 2, 3, 4):
                nodes = tuple(f"redis_{chr(97+i)}" for i in range(size))
                before = time.perf_counter_ns()
                placement = HashRing(RingSnapshot(1, vnodes, nodes)) if vnodes else Modulo(nodes)
                build_ns = time.perf_counter_ns() - before
                if size == 3:
                    ring3 = placement
                approximate_bytes = sys.getsizeof(placement)
                if vnodes:
                    approximate_bytes += (sys.getsizeof(placement._positions) + sum(map(sys.getsizeof, placement._positions))
                                          + sys.getsizeof(placement._owners) + sum(sys.getsizeof(n) for n in set(placement._owners)))
                builds.append(dict(trial=trial+1, seed=seed, algorithm=algorithm, vnodes=vnodes, nodes=size,
                                   build_ns=build_ns, estimated_ring_bytes=approximate_bytes))
                owners = [placement.locate(key) for key in keys]
                placements[size] = owners
                for workload in ("uniform_placement", "zipf_access"):
                    counts = Counter(owners) if workload == "uniform_placement" else Counter()
                    if workload == "zipf_access":
                        for index, frequency in accesses.items():
                            counts[owners[index]] += frequency
                    mean = count / size
                    cv = math.sqrt(sum((counts[n] - mean)**2 for n in nodes) / size) / mean
                    for node in nodes:
                        distribution.append(dict(trial=trial+1, seed=seed, algorithm=algorithm, vnodes=vnodes, nodes=size,
                                                 workload=workload, node_id=node, count=counts[node], total=count,
                                                 share=counts[node]/count, max_mean=max(counts.values())/mean, cv=cv))
                if sum(Counter(owners).values()) != count or not set(owners) <= set(nodes):
                    raise RuntimeError("invalid placement")
            for old, new in ((1, 2), (3, 4), (4, 3)):
                changed = sum(a != b for a, b in zip(placements[old], placements[new]))
                if vnodes:
                    for a, b in zip(placements[old], placements[new]):
                        if a != b and (b != "redis_d" if new == 4 else a != "redis_d" if old == 4 else b != "redis_b"):
                            raise RuntimeError("nonlocal ring movement")
                movement.append(dict(trial=trial+1, seed=seed, algorithm=algorithm, vnodes=vnodes,
                                     transition=f"{old}->{new}", changed_keys=changed, total=count, percent=100*changed/count))
            del placements
            # Same 100k timed calls/trial/config/concurrency; warmup excluded.
            for i in range(10000):
                ring3.locate(keys[i % count])
            for readers in (1, 4, 16):
                def batch(reader):
                    samples = []
                    for i in range(reader, 100000, readers):
                        key = keys[i % count]
                        before = time.perf_counter_ns()
                        ring3.locate(key)
                        samples.append(time.perf_counter_ns() - before)
                    return samples
                before = time.perf_counter_ns()
                if readers == 1:
                    samples = batch(0)
                else:
                    with ThreadPoolExecutor(max_workers=readers) as pool:
                        samples = [value for chunk in pool.map(batch, range(readers)) for value in chunk]
                elapsed = (time.perf_counter_ns() - before) / 1e9
                sample_file = raw / f"latency-{seed}-{algorithm}-{vnodes}-{readers}.json"
                sample_file.write_text(json.dumps(samples, separators=(",", ":")))
                raw_files.append(sample_file)
                samples.sort()
                summary.append(dict(trial=trial+1, seed=seed, level=args.level, algorithm=algorithm, vnodes=vnodes,
                                    nodes=3, readers=readers, key_count=count, attempted=100000, completed=len(samples),
                                    errors=0, elapsed_seconds=elapsed, throughput=len(samples)/elapsed,
                                    average_ns=sum(samples)/len(samples), p50_ns=percentile(samples,.50),
                                    p95_ns=percentile(samples,.95), p99_ns=percentile(samples,.99), min_ns=samples[0], max_ns=samples[-1]))
        print(f"{args.level} seed {seed}: complete", flush=True)
        if time.perf_counter() - wall_start > 600:
            raise RuntimeError("10 minute experiment bound exceeded")
    for name, rows in (("summary", summary), ("distribution", distribution), ("movement", movement), ("build", builds)):
        csv_write(output / f"{name}.csv", rows)
    bars(output / "latency.svg", "CPU lookup p95 (ns), three seeds, threads include GIL contention",
         [(f"s{r['seed']} {r['algorithm']}/{r['vnodes']} r{r['readers']}", r['p95_ns']) for r in summary])
    bars(output / "remapping.svg", "Changed logical keys (%)", [(f"s{r['seed']} {r['algorithm']}/{r['vnodes']} {r['transition']}", r['percent']) for r in movement])
    bars(output / "distribution.svg", "Seed 404, three nodes: placement and Zipf access shares", [(f"{r['algorithm']}/{r['vnodes']} {r['workload']} {r['node_id']}", r['share']) for r in distribution if r['seed'] == args.seed and r['nodes'] == 3])
    bars(output / "vnode_balance.svg", "Uniform placement max/mean, three nodes", [(f"s{r['seed']} {r['algorithm']}/{r['vnodes']}", r['max_mean']) for r in distribution if r['nodes']==3 and r['node_id']=='redis_a' and r['workload']=='uniform_placement'])
    manifest = dict(start_utc=started, end_utc=datetime.now(timezone.utc).isoformat(), level=args.level, seeds=list(range(args.seed,args.seed+3)),
                    python=sys.version, os=platform.platform(), cpu=platform.processor(), logical_cpus=__import__('os').cpu_count(),
                    hardware=subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize"], text=True).splitlines() if sys.platform=='darwin' else platform.machine(),
                    base_commit="45273ea7fd1ea53e335942b6c38f2d81d38856ee", component_checkout_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                    source_state="uncommitted source identified by hashes below; final commit in handoff", dependencies="Python stdlib; no runtime dependencies",
                    redis="not used", postgresql="not used", network="none", pool_size=None, resource_limits="host process, no imposed CPU/memory limit",
                    processes=1, threads=[1,4,16], nodes=[1,2,3,4], vnodes=[32,128,512], zipf_exponent=1.1, warmup_calls=10000,
                    timed_calls_per_case=100000, timer=time.get_clock_info("perf_counter")._asdict() if hasattr(time.get_clock_info("perf_counter"),"_asdict") else vars(time.get_clock_info("perf_counter")),
                    peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                    command=f"python3 experiments/phase4/consistent_hashing/run.py --seed {args.seed} --level {args.level} --output {output.relative_to(ROOT)}",
                    source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__), ROOT/'components/consistent_hashing/pulsegrid_consistent_hashing/__init__.py']},
                    raw_sha256={str(p.relative_to(ROOT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in raw_files},
                    output_sha256={p.name:sha(p) for p in sorted(output.iterdir())})
    lines=[f"# {args.level} measured CPU-only run", "",f"Keys: {count:,}; seeds {args.seed}–{args.seed+2}. Three trials; 100,000 timed calls per timing case, 10,000 warmup calls.",
           "", "No Redis, DB or hospital API integration measured. Latency surrounds complete locate including SHA256. Throughput includes timers, loop scheduling and thread pool creation; serialization/network/DB are not part of this pure algorithm. Closed-loop threads share immutable snapshots; GIL scheduling can raise tail latency and does not establish parallel CPU scaling. No fixed arrival target applies.",
           "", "| Algorithm/vnodes | 3→4 remap range % | one-reader throughput range /s | one-reader p95 range ns |", "|---|---:|---:|---:|"]
    for algorithm,v in (("modulo",0),("ring",32),("ring",128),("ring",512)):
        m=[r['percent'] for r in movement if r['algorithm']==algorithm and r['vnodes']==v and r['transition']=='3->4']
        t=[r for r in summary if r['algorithm']==algorithm and r['vnodes']==v and r['readers']==1]
        lines.append(f"| {algorithm}/{v} | {min(m):.3f}–{max(m):.3f} | {min(r['throughput'] for r in t):.0f}–{max(r['throughput'] for r in t):.0f} | {min(r['p95_ns'] for r in t)}–{max(r['p95_ns'] for r in t)} |")
    lines += ["", "distribution.csv reports per-node key and hot-access counts/shares, max/mean and population coefficient of variation; movement.csv uses changed logical owner/total. build.csv estimates retained ring allocation (excludes allocator overhead/build peak and snapshot metadata), with process peak RSS separately in manifest. Raw datasets/traces/timing samples are ignored within this exclusive experiment path; their hashes/sizes allow regeneration and verification. Timing hashes vary on reruns. Charts show every trial, not a selected best run. Uniform key balance does not guarantee hot-access balance."]
    for v in (32,128,512):
        lines += ["",f"ring/{v} compared to modulo (same-seed one-reader trials):"]
        for seed in range(args.seed,args.seed+3):
            b=next(r for r in summary if r['seed']==seed and r['vnodes']==0 and r['readers']==1)
            p=next(r for r in summary if r['seed']==seed and r['vnodes']==v and r['readers']==1)
            lines.append(f"- Seed {seed}: throughput baseline/proposed={b['throughput']/p['throughput']:.3f}, proposed−baseline={p['throughput']-b['throughput']:.0f}/s; mean latency baseline/proposed={b['average_ns']/p['average_ns']:.3f}, proposed−baseline={p['average_ns']-b['average_ns']:.1f}ns.")
    (output / "report.md").write_text("\n".join(lines)+"\n")
    manifest["output_sha256"] = {p.name: sha(p) for p in sorted(output.iterdir())}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


if __name__ == "__main__":
    main()
