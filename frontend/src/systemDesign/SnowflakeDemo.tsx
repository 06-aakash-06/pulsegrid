import { useRef, useState } from 'react';
import { Snowflake, decodeSnowflake, generateSnowflakes } from './algorithms/snowflake';
export function SnowflakeDemo() {
  const generator = useRef(new Snowflake(1, 0));
  const [id, setId] = useState<bigint | null>(null), [result, setResult] = useState(''), [busy, setBusy] = useState(false);
  const decoded = id === null ? null : decodeSnowflake(id);
  async function run() {
    setBusy(true); setResult('Generating and checking…');
    try {
      const start = performance.now(), ids = await generateSnowflakes(generator.current), elapsed = performance.now() - start;
      const unique = new Set(ids).size, ordered = ids.every((item, i) => i === 0 || item > ids[i - 1]);
      setId(ids.at(-1)!); setResult(`${ids.length.toLocaleString()} generated · ${ids.length - unique} collisions · strictly increasing: ${ordered ? 'yes' : 'no'} · ${elapsed.toFixed(2)} ms in this browser.`);
    } catch (error) { setResult(error instanceof Error ? error.message : 'Generator unavailable.'); } finally { setBusy(false); }
  }
  return <><p>Epoch: 2026-01-01 UTC · worker = service &lt;&lt; 7 | replica · service 1, replica 0.</p>
    <div className="lab-bits" aria-label="Snowflake layout">
      {([['Sign', '1 bit', 1, decoded?.sign], ['Time', '41 bits', 41, decoded?.time.toString()], ['Worker', '10 bits', 10, decoded?.worker], ['Sequence', '12 bits', 12, decoded?.sequence]] as const).map(([label, bits, width, value]) => <button key={label} type="button" style={{ flexGrow: width }} title={`${label}: ${value ?? 'generate first'}`} onClick={() => setResult(`${label}: ${value ?? 'generate first'} · ${bits}`)}>{label}<small>{bits}</small></button>)}
    </div><p className="lab-code">{id?.toString() ?? 'Generate to inspect an ID'}</p>
    <button data-tour="lab-snowflake" disabled={busy} onClick={() => void run()}>{busy ? 'Generating…' : 'Generate 10,000 IDs'}</button><p role="status">{result}</p>
    <small>Real bit packing, rollback rejection and sequence-overflow wait. This browser instance has no durable worker reservation, restart protection or cross-tab coordination; the server uses PostgreSQL for those.</small>
  </>;
}
