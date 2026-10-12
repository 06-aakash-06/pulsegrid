"""Validate measured evidence and aggregate all final trials."""
import csv
import hashlib
import json
from pathlib import Path

root=Path(__file__).parent
rows=[]
for name in ['verified-low','verified-medium','measured-high-1','measured-high-2','measured-high-3']:
    path=root/'results'/name
    manifest=json.loads((path/'manifest.json').read_text())
    # Early runs used the plan's root raw path; relocate only these experiment-owned files.
    renamed={}
    for raw, digest in manifest['samples_sha256'].items():
        p=Path(raw)
        if str(p).startswith('artifacts/phase4/unique_id/'):
            target=root/'artifacts'/p.parent.name/p.name
            target.parent.mkdir(parents=True,exist_ok=True)
            if p.exists(): p.rename(target)
            p=target
        assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
        renamed[str(p)]=digest
    manifest['samples_sha256']=renamed
    (path/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (path/'summary.csv').open() as f: rows.extend(csv.DictReader(f))
assert len(rows)==27
for row in rows:
    assert int(row['collisions'])==int(row['rejected'])==0
    assert int(row['generated'])==int(row['persisted'])==int(row['count'])
output=root/'results'/'combined'; output.mkdir(parents=True,exist_ok=True)
with (output/'summary.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
text='# Final measured comparison\n\nThree trials per mode/level. Closed-loop single-process asyncio, real loopback PostgreSQL 14. Pipeline includes allocator and INSERT; allocation latency includes ownership/committed range checks. No hospital endpoints mounted.\n\n| Level | Mode | IDs/s range | Pipeline p95 us range | Generation p95 us range | Measured IDs | Collisions |\n|---|---|---|---|---|---|---|\n'
means={}
comparisons=[]
for level in ['low','medium','high']:
    means[level]={}
    for mode in ['csprng','sequence','snowflake']:
        r=[row for row in rows if row['level']==level and row['mode']==mode]
        assert len(r)==3
        def bounds(key):
            values=[float(row[key]) for row in r]
            return f'{min(values):.1f}–{max(values):.1f}'
        means[level][mode]=sum(float(row['ids_per_second']) for row in r)/3
        text+=f"| {level} | {mode} | {bounds('ids_per_second')} | {bounds('p95_us')} | {bounds('generation_p95_us')} | {sum(int(row['count']) for row in r)} | 0 |\n"
    base=means[level]['csprng']; proposed=means[level]['snowflake']
    comparisons.append(f'{level}: mean CSPRNG/Snowflake throughput ratio {base/proposed:.3f}; absolute mean difference {base-proposed:.1f} IDs/s.')
text+='\n'+'\n\n'.join(comparisons)+'\n'
text+='\nZero observed collisions is finite evidence, not a guarantee against legacy IDs or duplicate assignments across independent databases. Allocators use per-client temporary PK tables plus a whole-trial uniqueness set; sequence baseline is technical nextval, not Records API. PostgreSQL 16, multi-process performance and coordinator hospital integration remain unexecuted.\n'
(output/'report.md').write_text(text)
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="720" height="400"><rect width="720" height="400" fill="white"/><text x="20" y="25">Mean pipeline throughput, IDs/second (three trials)</text>']
colors={'csprng':'#2563eb','sequence':'#9333ea','snowflake':'#dc2626'}
maximum=max(v for group in means.values() for v in group.values())
for i,(level,group) in enumerate(means.items()):
    for j,(mode,value) in enumerate(group.items()):
        x=65+i*215+j*45; height=value/maximum*260
        svg.append(f'<rect x="{x}" y="{320-height}" width="35" height="{height}" fill="{colors[mode]}"/><text x="{x}" y="{310-height}" font-size="10">{value:.0f}</text>')
    svg.append(f'<text x="{75+i*215}" y="345">{level}</text>')
for j,(mode,color) in enumerate(colors.items()): svg.append(f'<text x="{40+j*215}" y="380" fill="{color}">{mode}</text>')
svg.append('</svg>'); (output/'throughput.svg').write_text(''.join(svg))
print(text)
