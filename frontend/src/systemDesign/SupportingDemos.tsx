import { useRef, useState } from 'react';
import { useAuth } from '../auth/authContext';
import { useSimulation } from '../simulation/SimulationProvider';
import { createShortToken } from './algorithms/shortLink';
import { DemoCache } from './algorithms/cache';
import { FixtureCrawler } from './algorithms/crawler';
import { ServiceCall } from './ServiceCall';

export function ShortLinkDemo() {
  const { api, state } = useAuth();
  const simulation = useSimulation();
  const [sample, setSample] = useState<{ token: string; hash: string } | null>(null), [message, setMessage] = useState(''), [pending, setPending] = useState(false), [appointment, setAppointment] = useState('');
  async function generate() {
    setPending(true); try { setSample(await createShortToken()); } catch (error) { setMessage(String(error)); } finally { setPending(false); }
  }
  async function create() {
    setPending(true); setMessage('');
    try {
      const path = `/api/v1/appointments/${encodeURIComponent(appointment)}`;
      const workflow = await api.requestWithMetadata<{ version: number }>(`${path}/workflow`);
      const result = await api.request<{ short_path: string; expires_at: string }>(`${path}/short-links`, { method: 'POST', body: { purpose: 'appointment' }, ifMatch: workflow.etag ?? `"${workflow.data.version}"`, idempotencyKey: crypto.randomUUID(), referrerPolicy: 'no-referrer' });
      setMessage(`Owner created ${result.short_path} · expires ${result.expires_at}. Opening it still requires authorization.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Service unavailable.'); }
    finally { setPending(false); }
  }
  return <><p>128 random bits → 22-character Base62 → SHA-256 at rest. No custom aliases, click counter or Redis link cache.</p>
    <button data-tour="lab-links" disabled={pending} onClick={() => void generate()}>Generate random token</button>
    {sample && <div className="lab-token"><p><strong>Browser token</strong><code>{sample.token}</code></p><p><strong>Stored digest</strong><code>{sample.hash}</code></p></div>}
    <small>Browser sample only; this token is not a server link. Authentication, ownership, workflow state, revocation and expiry are checked by the service.</small>
    <label>Owned appointment ID<input inputMode="numeric" maxLength={19} value={appointment} onChange={e => setAppointment(e.target.value.replace(/\D/g, ''))} /></label>
    <button disabled={pending || state.status !== 'authenticated' || !/^[1-9]\d{0,18}$/.test(appointment)} onClick={() => void create()}>Call the real service · create link</button>
    <small>{simulation?.sampleBackend ? 'Dev mock has no short-link creation handler; an unavailable response is expected. Use a connected backend to issue a link.' : 'Creates an appointment-view link using its current ETag and an idempotency key. Patient/receptionist ownership rules apply.'}</small>
    <p role="status">{message}</p></>;
}
export function CacheDemo() {
  const cache = useRef(new DemoCache());
  const [key, setKey] = useState('doctor-directory'), [result, setResult] = useState('Read once to miss, then again to hit.'), [hits, setHits] = useState(0), [misses, setMisses] = useState(0);
  function read() {
    const entry = cache.current.read(key);
    if (entry.hit) setHits(value => value + 1); else setMisses(value => value + 1);
    setResult(`${entry.hit ? 'HIT · local cache' : 'MISS · synthetic owner read and refill'}: ${entry.value}`);
  }
  return <><label>Directory cache key<input maxLength={80} value={key} onChange={e => setKey(e.target.value)} /></label>
    <div className="lab-flow"><span>Directory request</span><span>→ TTL cache</span><span>→ owner database on miss</span></div>
    <div className="lab-controls"><button data-tour="lab-cache" onClick={read}>Read directory</button><button onClick={() => { cache.current.invalidate(); setResult('Epoch invalidated: next read must miss.'); }}>Invalidate cache</button></div>
    <p role="status">{result}</p><p>Hits {hits} · misses {misses} · local TTL 10 seconds</p>
    <small>No network latency is simulated here. No mutex stampede lock was implemented. The owner database remains authoritative.</small>
    <ServiceCall path="/api/v1/doctors?limit=10" />
  </>;
}
export function CrawlerDemo() {
  const crawler = useRef(new FixtureCrawler());
  const [log, setLog] = useState<string[]>([]), [busy, setBusy] = useState(false), [version, setVersion] = useState(1);
  async function ingest(kind: 'refresh' | 'conflict' | 'recover') {
    setBusy(true);
    const revision = kind === 'recover' ? version + 1 : version;
    try {
      // Seed a known revision before trying its conflicting content.
      const seed = kind === 'conflict' ? await crawler.current.ingest({ host: 'synthetic-provider.fixture', version: revision, content: 'coverage:80' }) : [];
      const lines = await crawler.current.ingest({ host: 'synthetic-provider.fixture', version: revision, content: kind === 'conflict' ? 'coverage:90' : 'coverage:80' });
      setLog(previous => [...previous, ...seed, ...lines].slice(-24)); setVersion(revision);
    } catch (error) { setLog(previous => [...previous, String(error)]); } finally { setBusy(false); }
  }
  return <><p>Allowlisted synthetic fixture host only. No external crawling, robots.txt or conditional ETag fetches.</p>
    <div className="lab-controls"><button data-tour="lab-crawler" disabled={busy} onClick={() => void ingest('refresh')}>Fetch fixture</button><button disabled={busy} onClick={() => void ingest('conflict')}>Try revision conflict</button><button disabled={busy} onClick={() => void ingest('recover')}>Publish next revision</button></div>
    <pre className="lab-log" role="log" aria-label="Crawler log" aria-live="polite">{log.length ? log.join('\n') : 'Ready: fetch → validate → dedupe → estimate\nConflict → quarantine → estimate blocked'}</pre>
    <small>Local fixture state machine, not a network fetch or an insurance coverage decision.</small></>;
}
const databases = ['Patient', 'Doctor', 'Appointment', 'Records', 'Pharmacy', 'Billing', 'Emergency'];
export function IsolationDemo() {
  const [blocked, setBlocked] = useState(false);
  return <><div className="lab-databases" aria-label="Seven independently owned databases">{databases.map(name => <div key={name}><span aria-hidden="true">▤</span><strong>{name}</strong><small>Private PostgreSQL</small></div>)}</div>
    <button data-tour="lab-isolation" onClick={() => setBlocked(true)}>Try cross-database join</button>
    {blocked && <div className="lab-blocked" role="status"><strong>Blocked by service ownership</strong><p>Illustration: the UI sends no SQL. Each service has credentials for its own database. Use owner APIs or events.</p>
      <ol><li>Billing transaction: payment + audit + outbox + idempotency response</li><li>Outbox publisher → RabbitMQ → Appointment consumer</li><li>Appointment transaction: inbox dedupe + projection + outgoing outbox</li><li>Acknowledge after commit; reconcile with authenticated owner APIs</li></ol></div>}
    <small>At-least-once delivery; no global transaction. These are service databases, not shards of one table.</small>
    <ServiceCall path="/api/v1/appointments/operations/control-room/summary" />
  </>;
}
