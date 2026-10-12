"""Live unchanged-revision polling must not rebuild indexes repeatedly."""
import subprocess,time,json
from pathlib import Path
owners=['doctor','pharmacy']
def read(owner):
 text=subprocess.check_output(['docker','exec',f'pulsegrid-{owner}-1','python','-c',"import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())"],text=True)
 fields={line.rsplit(' ',1)[0]:float(line.rsplit(' ',1)[1]) for line in text.splitlines() if 'index_rebuild_seconds_count' in line and 'outcome="success"' in line}
 assert fields
 return fields
before={o:read(o) for o in owners};time.sleep(16);after={o:read(o) for o in owners};assert before==after,(before,after)
Path('experiments/phase4/integration/results/index-poll-cost.json').write_text(json.dumps({'observed_seconds':16,'before':before,'after':after,'unchanged_index_rebuilds':0},indent=2));print('PASS live revision polling: zero unnecessary rebuilds across16s')
