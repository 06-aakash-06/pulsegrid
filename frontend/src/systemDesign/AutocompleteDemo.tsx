import { useMemo, useState } from 'react';
import { generatedCatalog, Trie, raceAutocomplete } from './algorithms/trie';
import { ServiceCall } from './ServiceCall';
export function AutocompleteDemo() {
  const [prefix, setPrefix] = useState('doctor 00'), [size, setSize] = useState(10000), [race, setRace] = useState(''), [busy, setBusy] = useState(false);
  const words = useMemo(() => generatedCatalog(size), [size]);
  const trie = useMemo(() => new Trie(words), [words]);
  const matches = trie.search(prefix);
  async function run() {
    setBusy(true); await new Promise(resolve => setTimeout(resolve, 20));
    const result = raceAutocomplete(words, prefix);
    setRace(`Median per lookup: trie ${result.trieMs.toFixed(5)} ms · linear scan ${result.scanMs.toFixed(5)} ms (${result.runs} alternating runs × ${result.batch} lookups).`); setBusy(false);
  }
  return <><label>Prefix<input data-tour="lab-autocomplete" maxLength={40} value={prefix} onChange={e => { setPrefix(e.target.value); setRace(''); }} /></label>
    <label>Generated catalog<select value={size} onChange={e => { setSize(Number(e.target.value)); setRace(''); }}><option value={1000}>1,000 entries</option><option value={10000}>10,000 entries</option><option value={25000}>25,000 entries</option></select></label>
    <div className="lab-trie" aria-label="Prefix branch"><span>root</span>{[...prefix].map((char, i) => <span key={i}>→ {char === ' ' ? '␠' : char}</span>)}<span>→ {matches.length ? 'matches' : 'no branch'}</span></div>
    <ul className="lab-matches">{matches.slice(0, 4).map(word => <li key={word}>{word}</li>)}</ul>
    <button disabled={busy} onClick={() => void run()}>{busy ? 'Timing…' : 'Race trie vs linear scan'}</button><p role="status">{race}</p>
    <small>In-browser demo over generated data; index construction excluded. Browser clock precision and device load affect these medians. Lab baseline was sorted-prefix, not SQL.</small>
    <ServiceCall path={`/api/v1/doctors/autocomplete?prefix=${encodeURIComponent(prefix)}&limit=10`} label="Call the real service · doctors" />
    <ServiceCall path={`/api/v1/pharmacy/medicines/autocomplete?prefix=${encodeURIComponent(prefix)}&limit=10`} label="Call the real service · medicines" />
  </>;
}
