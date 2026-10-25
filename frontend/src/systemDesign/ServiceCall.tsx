import { useState } from 'react';
import { useAuth } from '../auth/authContext';
import { useSimulation } from '../simulation/SimulationProvider';

/** Uses the normal authenticated client; authorization remains with the owner. */
export function ServiceCall({ path, label = 'Call the real service' }: { path: string; label?: string }) {
  const { api, state } = useAuth();
  const simulation = useSimulation();
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState('');
  async function call() {
    setPending(true); setResult('');
    try { const response = await api.request<unknown>(path); setResult(JSON.stringify(response, null, 2)); }
    catch (error) { setResult(error instanceof Error ? error.message : 'Service unavailable.'); }
    finally { setPending(false); }
  }
  return <div className="lab-service"><button type="button" disabled={pending || state.status !== 'authenticated'} onClick={() => void call()}>{pending ? 'Calling…' : label}</button>
    <small>{simulation?.sampleBackend ? 'Connected to dev/demo mock API · synthetic response' : 'Authenticated owner API · your permissions apply'}</small>
    {state.status !== 'authenticated' && <small>Sign in to call the service.</small>}
    {result && <pre role="status" className="lab-response">{result}</pre>}
  </div>;
}
