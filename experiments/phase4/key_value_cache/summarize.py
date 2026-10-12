"""Recompute bounded final comparisons and verify all retained raw sample hashes."""
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root=Path(__file__).parent
lines=['# Phase 4.3 measured evidence','','All rows measure the unmounted Doctor projection adapter plus real owner PostgreSQL/Redis, not authenticated HTTP or final owner wire reconstruction. Placement is a two-node modulo harness, not Agent2 ring.','',
       'Full diagnostic:5s warmup/30s measurement, primary-key-only fixture. Indexed sensitivity:0.2s/3s, existing Doctor query secondary indexes. Each uses three trials (seeds404/405/406). Neither completes the frozen integrated endpoint gate.','']
comparisons=[]; total=0
for suffix,title in [('final','Full-duration unindexed diagnostics'),('indexed','Short existing-index sensitivity')]:
    lines += ['## '+title,'','| Level | Scenario | Mean ms | p95 ms | Reads/s | Hit ratio |','|---|---|---:|---:|---:|---:|']
    for level in ['low','medium','high']:
        path=root/'results'/f'{level}-{suffix}'
        manifest=json.loads((path/'manifest.json').read_text())
        assert hashlib.sha256(Path(manifest['raw_path']).read_bytes()).hexdigest()==manifest['raw_sha256']
        for source,digest in manifest['source_hashes'].items():
            assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==digest, source
        ET.parse(path/'latency.svg')
        rows=list(csv.DictReader((path/'summary.csv').open()))
        assert len(rows)==15 and all(int(r['errors'])==0 for r in rows)
        assert sum(int(r['completed']) for r in rows)==manifest['request_count']
        total+=manifest['request_count']
        for scenario in ['uncached','cold','warm','invalidation','redis_failure']:
            group=[r for r in rows if r['scenario']==scenario]
            assert len(group)==3
            average=lambda field: sum(float(r[field]) for r in group)/3
            hits=sum(int(r['hits']) for r in group); misses=sum(int(r['misses']) for r in group)
            hit=f'{hits/(hits+misses):.2%}' if hits+misses else 'n/a'
            lines.append(f"| {level} | {scenario} | {average('mean_ms'):.3f} | {average('p95_ms'):.3f} | {average('throughput'):.1f} | {hit} |")
            if scenario!='uncached':
                for row in group:
                    baseline=next(r for r in rows if r['trial']==row['trial'] and r['scenario']=='uncached')
                    comparisons.append(dict(fixture=suffix,level=level,trial=row['trial'],scenario=scenario,
                                            baseline_to_cache_mean_ratio=float(baseline['mean_ms'])/float(row['mean_ms']),
                                            cache_minus_baseline_mean_ms=float(row['mean_ms'])-float(baseline['mean_ms']),
                                            cache_to_baseline_throughput_ratio=float(row['throughput'])/float(baseline['throughput']),
                                            baseline_minus_cache_db_queries_per_read=int(baseline['db_queries'])/int(baseline['completed'])-int(row['db_queries'])/int(row['completed'])))
    lines += ['']
lines += [f'{total:,} successful measured reads across90 final/sensitivity trials; zero measured read errors. Owned storage cleanup and post-outage Redis recovery checks passed. Superseded low smoke is excluded.','',
          'Tables average trial means/p95/throughput; hit ratio pools hit/miss counts. p95 is nearest-rank per trial, not a pooled percentile. Each source/hash/raw count and complete per-trial variation is retained. comparisons.csv gives ratios and absolute latency/query deltas matched by trial.','',
          'Every cache request still reads a PostgreSQL revision. Warm caching avoids expensive projection SQL but does not reduce total SQL query count versus the one-statement baseline; misses add a projection read. Redis failures are excluded from hit/(hit+miss) and recorded separately, including their p95/p99 latency.','',
          'Cold preparation deletes a key before each read; concurrent repopulation can yield hits. Cold throughput includes preparation, but latency/application DB counts exclude its extra revision read/delete. The hot-query share is50/80/95 percent over a ten-key working set, not an exact repeated-key probability. Two cache objects share one adapter process.','',
          'No real ring, authenticated endpoint, final Alembic revision triggers, fresh wire fields, Compose ACL/networking, browser or full hospital regressions were verified. These are coordinator-only integration gates; Phase4 acceptance remains incomplete. The initial final low cold trial overlapped roughly5s of local test activity.','']
(root/'RESULTS.md').write_text('\n'.join(lines))
with (root/'comparisons.csv').open('w') as output:
    writer=csv.DictWriter(output,fieldnames=list(comparisons[0]),lineterminator='\n'); writer.writeheader(); writer.writerows(comparisons)
for csv_path in root.rglob('*.csv'):
    csv_path.write_text(csv_path.read_text())  # Preserve values; normalize generated CRLF to LF.
print(f'verified6 manifests,6 raw hashes,6 SVGs,90 trials,{total} reads; wrote RESULTS.md/comparisons.csv')
