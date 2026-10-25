import { useEffect, useRef, useState } from 'react';
import { HashRing, HASH_SPACE, hashKey, comparePlacement, type RingPoint } from './algorithms/hashRing';
const colors = ['#247b78', '#b16635', '#626b9d', '#789545', '#a45f7d', '#4e8396'];
const fraction = (position: bigint) => Number(position >> 204n) / 2 ** 52;
const xy = (angle: number, radius = 78) => ({ x: 110 + Math.sin(angle) * radius, y: 110 - Math.cos(angle) * radius });
function RingVisual({ points, keyPosition }: { points: RingPoint[]; keyPosition: bigint | null }) {
  return <svg className="lab-ring" viewBox="0 0 220 220" role="img" aria-label="SHA-256 ring, coloured ownership arcs and test key position">
    <circle cx="110" cy="110" r="78" fill="none" stroke="#d9d0c4" strokeWidth="15" />
    {points.map((point, index) => {
      const previous = points[(index + points.length - 1) % points.length];
      const start = fraction(previous.position) * Math.PI * 2;
      const end = fraction(point.position) * Math.PI * 2;
      const from = xy(start), to = xy(end);
      const delta = (end - start + Math.PI * 2) % (Math.PI * 2);
      return <path key={`${point.node}-${index}`} d={`M${from.x} ${from.y} A78 78 0 ${delta > Math.PI ? 1 : 0} 1 ${to.x} ${to.y}`} fill="none" stroke={colors[Number(point.node.split('_').at(-1)) - 1]} strokeWidth="15"><title>{point.node}: clockwise ownership</title></path>;
    })}
    {keyPosition !== null && <circle {...(() => { const p = xy(fraction(keyPosition) * Math.PI * 2, 93); return { cx: p.x, cy: p.y }; })()} r="5" fill="#243e3d"><title>Test key</title></circle>}
    <text x="110" y="106" textAnchor="middle" fill="#243e3d" fontSize="15">Clockwise lookup</text><text x="110" y="128" textAnchor="middle" fill="#496362" fontSize="12">SHA-256 · 128 vnodes</text>
  </svg>;
}
export function HashingDemo() {
  const [nodes, setNodes] = useState(3), [busy, setBusy] = useState(false), [message, setMessage] = useState('Add or remove a node to compute placement changes.');
  const [ring, setRing] = useState<HashRing | null>(null), [testKey, setTestKey] = useState('doctor-directory'), [testResult, setTestResult] = useState('');
  const [position, setPosition] = useState<bigint | null>(null);
  useEffect(() => { let active = true; void HashRing.create(['redis_1', 'redis_2', 'redis_3']).then(value => { if (active) setRing(previous => previous ?? value); }).catch(error => { if (active) setMessage(String(error)); }); return () => { active = false; }; }, []);
  const keys = useRef<bigint[] | null>(null);
  const names = (count: number) => Array.from({ length: count }, (_, i) => `redis_${i + 1}`);
  async function change(next: number) {
    setBusy(true); setTestResult('');
    try {
      const [before, after] = await Promise.all([HashRing.create(names(nodes)), HashRing.create(names(next))]);
      // Yield between bounded batches instead of blocking rendering on 10k digests.
      if (!keys.current) {
        const generated: bigint[] = [];
        for (let offset = 0; offset < 10000; offset += 250) {
          generated.push(...await Promise.all(Array.from({ length: 250 }, (_, i) => hashKey(`synthetic-${offset + i}`))));
          await new Promise(resolve => setTimeout(resolve, 0));
        }
        keys.current = generated;
      }
      const result = comparePlacement(before, after, keys.current);
      setMessage(`${nodes} → ${next} nodes · ${result.total.toLocaleString()} keys: ring ${result.ringMoved.toLocaleString()} moved (${(result.ringMoved / result.total * 100).toFixed(2)}%); modulo ${result.moduloMoved.toLocaleString()} moved (${(result.moduloMoved / result.total * 100).toFixed(2)}%).`);
      setNodes(next); setRing(after); setPosition(null);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to hash.'); }
    finally { setBusy(false); }
  }
  async function locate() {
    setBusy(true);
    try {
      const current = ring ?? await HashRing.create(names(nodes)); const pos = await hashKey(testKey);
      setRing(current); setPosition(pos); setTestResult(`${testKey || '(empty key)'} → ${current.locate(pos)} · ${fraction(pos).toFixed(4)} of the hash space`);
    } catch (error) { setTestResult(String(error)); } finally { setBusy(false); }
  }
  return <><div className="lab-ring-layout"><RingVisual points={ring?.points ?? []} keyPosition={position} /><div className="lab-legend">{names(nodes).map((node, i) => <span key={node}><i style={{ background: colors[i] }} />{node}</span>)}</div></div>
    <div className="lab-controls"><button data-tour="lab-hashing" disabled={busy || nodes >= 6} onClick={() => void change(nodes + 1)}>Add node</button><button disabled={busy || nodes <= 2} onClick={() => void change(nodes - 1)}>Remove node</button></div>
    <p role="status">{busy ? 'Computing SHA-256 placement…' : message}</p>
    <label>Test key<input maxLength={80} value={testKey} onChange={e => setTestKey(e.target.value)} /></label><button disabled={busy} onClick={() => void locate()}>Locate key</button><p role="status">{testResult}</p>
    <small>Same full digest for both placements. {String(HASH_SPACE.toString(2).length - 1)}-bit hash space; no replication or automatic failover.</small></>;
}
