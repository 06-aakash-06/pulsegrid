"""Retain and summarize exact before/after raw evidence; no sensitive IDs/tokens."""
import csv,json,gzip,hashlib,statistics,shutil
from pathlib import Path
out=Path('experiments/phase4/integration/results');out.mkdir(parents=True,exist_ok=True)
raw=Path('artifacts/phase4/short-links');raw.mkdir(parents=True,exist_ok=True)
rows=[];manifest={}
for label in ['before','after','low','medium','diagnostic']:
 source=Path(f'/tmp/pulsegrid-phase4-short-{label}.json');x=json.loads(source.read_text())
 sample=Path(f'/tmp/pulsegrid-phase4-short-{label}.samples.csv');data=list(csv.DictReader(sample.open()))
 with gzip.open(raw/(label+'.csv.gz'),'wb') as f:f.write(sample.read_bytes())
 (raw/(label+'.json')).write_bytes(source.read_bytes())
 manifest[label]={'sha256':hashlib.sha256(sample.read_bytes()).hexdigest(),'raw':str(raw/(label+'.csv.gz')),'environment':x['environment'],'seed':x['seed'],'clients':x['clients'],'duration':x['measurement_seconds_per_mode_per_trial'],'fixture_rows':x['total_fixture_future_appointments'],'error_classes':__import__('collections').Counter(r.get('error_type','unrecorded') for r in data if int(r['status_code']) not in (200,201,303))}
 for trial in x['trials']:
  for mode in ['baseline','proposed']:
   for op,summary in trial[mode]['operations'].items():
    subset=[r for r in data if int(r['trial'])==trial['trial']-1 and r['mode']==mode and r['operation']==op]
    lat=[float(r['latency_ms']) for r in subset];success=[float(r['latency_ms']) for r in subset if int(r['status_code']) in (200,201,303)]
    rows.append({'version':label,'trial':trial['trial'],'operation':op,'attempted':len(lat),'errors':summary['errors'],'mean_all_ms':statistics.mean(lat),'success_p50_ms':statistics.median(success) if success else None,'success_p95_ms':sorted(success)[__import__('math').ceil(.95*len(success))-1] if success else None,'successful_throughput':summary['completed']/trial[mode]['elapsed_seconds'],'error_rate':summary['errors']/len(lat)})
with (out/'short-links-before-after.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
(out/'short-links-manifest.json').write_text(json.dumps(manifest,indent=2))
print('raw files preserved; measured rows',len(rows))
