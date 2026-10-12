"""Full-duration indexed adapter comparisons with the actual production ring."""
import sys,asyncio,argparse,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/phase4/key_value_cache'))
import run,fixtures
from run_indexed import INDEX_DDL
from pulsegrid_consistent_hashing import HashRing,RingSnapshot
parser=argparse.ArgumentParser();parser.add_argument('--level',choices=['low','medium','high'],required=True);args=parser.parse_args()
fixtures.DDL.extend(INDEX_DDL)
run.Placement=lambda:HashRing(RingSnapshot(1,128,('cache_a','cache_b')))
args.seed=404;args.warmup=5.;args.duration=30.;args.output=str(ROOT/'experiments/phase4/integration/results'/('cache-ring-'+args.level))
asyncio.run(run.main(args))
p=Path(args.output)/'manifest.json';m=json.loads(p.read_text());m['topology']='one adapter process, two cache objects, two real Redis nodes, actual immutable HashRing';m['limitations']=[v.replace('No real consistent ring or HA claim.','Actual ring placement is used; placement provides no replication/HA.') for v in m['limitations']];m['resources']={'peak_process_rss_bytes':__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss,'cpu_user_seconds':__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_utime,'cpu_system_seconds':__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_stime};m['integration_placement']='actual HashRing locate/epoch;128 vnodes;2 Redis nodes';m['query_indexes']=INDEX_DDL;m['source_hashes'][str(Path(__file__).relative_to(ROOT))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();p.write_text(json.dumps(m,indent=2)+'\n')
r=Path(args.output)/'report.md';r.write_text(r.read_text().replace('No real consistent ring or HA claim.','Actual HashRing placement is used; no replication/HA claim.'))
with r.open('a') as f:f.write('\nCoordinator rerun: actual production HashRing placement, existing Doctor query indexes, full5s warmup/30s x3. This remains a storage adapter benchmark; authenticated endpoint samples are separate.\n')
