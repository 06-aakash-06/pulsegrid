"""Retain raw inputs/timings from the unchanged CPU comparison harness.

High timing uses its explicit512MiB experimental cap; default64MiB denial is
retained in default_cap.csv. This never changes deployment limits or API behavior.
"""
import sys,importlib.util,inspect,gzip,csv,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('autocomplete_cpu_evidence',ROOT/'experiments/phase4/autocomplete/run.py');bench=importlib.util.module_from_spec(spec);sys.modules[spec.name]=bench;spec.loader.exec_module(bench)
level=sys.argv[sys.argv.index('--level')+1]
raw=ROOT/'artifacts/phase4/autocomplete'/('retained-'+level);raw.mkdir(parents=True,exist_ok=False)
original=bench._measure_calls;records=0
with gzip.open(raw/'samples.csv.gz','wt') as stream:
 writer=csv.writer(stream,lineterminator='\n');writer.writerow(['owner','trial','algorithm','clients','result_limit','trace_index','workload','latency_ns'])
 def measured(search,trace,clients,result_limit):
  global records
  frame=inspect.currentframe().f_back.f_locals
  algorithm=next((name for name,key in [('trie','trie_search'),('sorted_prefix_baseline','baseline_search'),('python_scan_secondary','scan_search')] if search is frame[key]),'unknown')
  result=original(search,trace,clients,result_limit)
  indices=(i for worker in range(clients) for i in range(worker,len(trace),clients))
  for index,latency in zip(indices,result[0]):writer.writerow([frame['owner'],frame['trial']+1,algorithm,clients,result_limit,index,trace[index][0],latency]);records+=1
  stream.flush();return result
 bench._measure_calls=measured
 bench.main()
seed=int(sys.argv[sys.argv.index('--seed')+1]) if '--seed' in sys.argv else 404
catalogs=bench.generate_catalogs(bench.LEVEL_ENTRIES[level],seed)
inputs=json.dumps({owner:[{'id':x.id,'kind':x.kind,'label':x.label} for x in entries] for owner,entries in catalogs.items()},ensure_ascii=False,sort_keys=True).encode()
with gzip.open(raw/'catalog.json.gz','wb') as stream:stream.write(inputs)
out=Path(sys.argv[sys.argv.index('--output')+1]);path=out/'manifest.json';m=json.loads(path.read_text());m['raw_samples_or_datasets_retained']=True;m['raw_evidence']={'samples':str((raw/'samples.csv.gz').relative_to(ROOT)),'samples_sha256':hashlib.sha256((raw/'samples.csv.gz').read_bytes()).hexdigest(),'sample_count':records,'catalog':str((raw/'catalog.json.gz').relative_to(ROOT)),'catalog_uncompressed_sha256':hashlib.sha256(inputs).hexdigest()};m['capture_note']='Samples serialized after complete timed batch; raw capture RSS is included in process RSS. High timed512MiB is an experimental algorithm diagnostic; deployed64MiB remains unchanged and high default_cap denial is retained.';path.write_text(json.dumps(m,indent=2)+'\n');print('PASS raw CPU inputs/timings retained',records)
