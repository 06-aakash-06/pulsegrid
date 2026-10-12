"""Real ring with independently owned disposable Redis nodes; bounded recovery."""
import asyncio,json,statistics,sys,time,hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'key_value_cache'))
from fixtures import storage
from pulsegrid_consistent_hashing import HashRing,RingSnapshot,Node
from pulsegrid_key_value_cache import Cache,CacheEntry,redis_client
async def main():
 # This fixture owns its Redis processes and PostgreSQL; no retained stack outage.
 with storage(3) as (dsn,ports,processes):
  nodes=('cache_a','cache_b');clients={n:redis_client(f'redis://127.0.0.1:{p}') for n,p in zip(nodes+('cache_c',),ports)}
  ring=HashRing(RingSnapshot(1,128,nodes));cache=Cache(ring,clients)
  keys=[f'seed404:{i}'.encode() for i in range(10000)];counts=Counter(ring.locate(k) for k in keys)
  expiry=time.time_ns()//1000000+30000
  lat=[]
  for key in keys:
   start=time.perf_counter_ns();await cache.set(key,CacheEntry(b'synthetic-directory',1,expiry),30000);lat.append((time.perf_counter_ns()-start)/1e6)
  physical={n:await clients[n].dbsize() for n in nodes}
  assert physical==dict(counts), (physical,counts)
  # Add a third owned Redis through the fixture helper, same bounded local topology.
  # The fixture exports only two servers; simulate removal on real nodes, and
  # addition movement separately until an independent third server is launched.
  removed=ring.without_node('cache_b',2);second=Cache(removed,clients)
  assert await second.get(keys[0]) is None
  await second.set(keys[0],CacheEntry(b'fresh',2,expiry),30000)
  assert (await second.get(keys[0])).source_version==2
  added=ring.with_node(Node('cache_c'),3)
  third=Cache(added,clients)
  assert await third.get(keys[0]) is None
  for key in keys:await third.set(key,CacheEntry(b'fresh-epoch3',3,expiry),30000)
  added_counts=Counter(added.locate(k) for k in keys)
  actual_added={node:len(await client.keys('pg:cache:v1:doctor:3:*')) for node,client in clients.items()}
  assert actual_added==dict(added_counts)
  await third.set(b'ttl',CacheEntry(b'expire',3,time.time_ns()//1000000+100),100)
  await asyncio.sleep(.12)
  assert await third.get(b'ttl') is None
  await third.delete(keys[0]);assert await third.get(keys[0]) is None
  movement=sum(ring.locate(k)!=added.locate(k) for k in keys)/len(keys)
  modulo=lambda k,ns:ns[int.from_bytes(hashlib.sha256(b'pg-ring-key-v1\0'+k).digest(),'big')%len(ns)]
  modulo_movement=sum(modulo(k,nodes)!=modulo(k,nodes+('cache_c',)) for k in keys)/len(keys)
  result={'seed':404,'keys':len(keys),'physical_counts':physical,'ring_add_movement':movement,'modulo_add_movement':modulo_movement,'epoch_miss':True,'set_mean_ms':statistics.mean(lat),'set_p95_ms':sorted(lat)[9499],'added_actual_counts':actual_added,'ttl_delete':True,'limitations':['No replication or HA claim.']}
  out=Path('experiments/phase4/integration/results');out.mkdir(parents=True,exist_ok=True);(out/'cache-topology.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
  await cache.close()
asyncio.run(main())
