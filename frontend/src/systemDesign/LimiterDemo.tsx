import { useRef, useState } from 'react';
import { TokenBucket, surgeBudget, type TrafficClass } from './algorithms/tokenBucket';
import { ServiceCall } from './ServiceCall';
export function LimiterDemo() {
  const [capacity, setCapacity] = useState(60), [rate, setRate] = useState(10), [burst, setBurst] = useState(160);
  const [surge, setSurge] = useState(false), [traffic, setTraffic] = useState<TrafficClass>('C');
  const [counts, setCounts] = useState({ accepted: 0, rejected: 0 }), [tokens, setTokens] = useState(60);
  const bucket = useRef<TokenBucket | null>(null);
  const effective = surgeBudget(capacity, traffic, surge), refill = surgeBudget(Math.round(rate * 1000), traffic, surge) / 1000;
  const reset = () => { bucket.current = null; setCounts({ accepted: 0, rejected: 0 }); setTokens(effective); };
  function fire() {
    bucket.current ??= new TokenBucket(effective, refill);
    const result = bucket.current.burst(burst);
    setCounts(previous => ({ accepted: previous.accepted + result.accepted, rejected: previous.rejected + result.rejected }));
    setTokens(bucket.current.tokens);
  }
  return <><div className="lab-fields"><label>Capacity<input type="number" min="1" max="10000" value={capacity} onChange={e => { setCapacity(Math.min(10000, Math.max(1, Math.floor(Number(e.target.value))))); bucket.current = null; setCounts({ accepted: 0, rejected: 0 }); }} /></label>
    <label>Refill / second<input type="number" min="0.001" step="0.001" max="10000" value={rate} onChange={e => { setRate(Math.min(10000, Math.max(.001, Number(e.target.value)))); bucket.current = null; setCounts({ accepted: 0, rejected: 0 }); }} /></label>
    <label>Burst requests<input type="number" min="1" max="10000" value={burst} onChange={e => setBurst(Math.min(10000, Math.max(1, Math.floor(Number(e.target.value)))))} /></label>
    <label>Traffic class<select value={traffic} onChange={e => { setTraffic(e.target.value as TrafficClass); bucket.current = null; setCounts({ accepted: 0, rejected: 0 }); }}><option value="A">A · critical</option><option value="B">B · important</option><option value="C">C · deferrable</option></select></label></div>
    <label className="lab-checkbox"><input type="checkbox" checked={surge} onChange={e => { setSurge(e.target.checked); bucket.current = null; setCounts({ accepted: 0, rejected: 0 }); }} />Surge Mode</label>
    <p>Effective capacity {effective.toFixed(2)} · refill {refill.toFixed(2)}/s. Single-replica floor: at least one whole token. Policy edits create a fresh teaching bucket.</p>
    <progress max={effective} value={bucket.current ? tokens : effective} aria-label="Tokens remaining" />
    <div className="lab-controls"><button data-tour="lab-limiter" onClick={fire}>Fire burst</button><button onClick={() => { bucket.current ??= new TokenBucket(effective, refill); bucket.current.refill(); setTokens(bucket.current.tokens); }}>Refill to now</button><button onClick={reset}>Reset bucket</button></div>
    <p role="status">Accepted {counts.accepted} · rejected {counts.rejected} · tokens {(bucket.current ? tokens : effective).toFixed(2)}</p>
    <small>This single bucket demonstrates token accounting. The backend also enforces finite source and aggregate quotas; class A is not unlimited.</small>
    <ServiceCall path="/api/v1/appointments/operations/control-room/summary" />
  </>;
}
