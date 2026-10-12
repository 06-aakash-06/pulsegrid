"""Render measured summaries/raw latency samples with matplotlib, without rerunning workloads."""
import csv
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).parent/'results'
colors={'csprng':'#2563eb','sequence':'#9333ea','snowflake':'#dc2626'}
with (root/'combined'/'summary.csv').open() as f: rows=list(csv.DictReader(f))
fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
for j,mode in enumerate(colors):
    averages=[]; lower=[]; upper=[]
    for level in ['low','medium','high']:
        values=[float(r['ids_per_second']) for r in rows if r['mode']==mode and r['level']==level]
        avg=sum(values)/len(values)
        averages.append(avg); lower.append(avg-min(values)); upper.append(max(values)-avg)
    ax.bar([i+(j-1)*.24 for i in range(3)],averages,width=.24,label=mode,color=colors[mode],yerr=[lower,upper],capsize=4)
ax.set_xticks([0,1,2],['Low: 1 worker','Medium: 4 workers','High: 16 workers'])
ax.set_ylabel('Allocation + INSERT, IDs/second')
ax.set_title('Measured throughput: mean with min/max across three trials')
ax.legend();ax.grid(axis='y',alpha=.2)
fig.savefig(root/'combined'/'throughput.svg');fig.savefig('/tmp/pulsegrid-id-throughput-preview.png',dpi=140)
plt.close(fig)
for name in ['verified-low','verified-medium','measured-high-1','measured-high-2','measured-high-3']:
    path=root/name
    m=json.loads((path/'manifest.json').read_text())
    fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
    selected={}
    for raw in m['samples_sha256']:
        mode=Path(raw).name.split('-')[0]
        selected[mode]=raw  # final trial for that mode in this run
    for mode,raw in selected.items():
        s=sorted(json.loads(Path(raw).read_text())['pipeline_ns'])
        xs=[s[math.ceil(q/100*len(s))-1]/1000 for q in range(1,101)]
        ax.plot(xs,range(1,101),label=mode,color=colors[mode])
    ax.set_xscale('log');ax.set_xlabel('Allocation + INSERT latency, microseconds (log scale)')
    ax.set_ylabel('Cumulative percent');ax.set_title(f'{name}: latency CDF, last trial')
    ax.legend();ax.grid(alpha=.2);fig.savefig(path/'latency.svg');plt.close(fig)
print('Six standalone SVG figures rendered.')
