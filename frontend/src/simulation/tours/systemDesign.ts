import type { Tour } from '../types';
import { measuredResults } from '../../systemDesign/measuredResults';
export const systemDesignTour: Tour = {
  id: 'system-design', role: null, workspace: null, roleLabel: 'System Design Lab',
  title: 'The seven components behind PulseGrid', goal: 'Run the algorithms and separate browser experiments from lab evidence.',
  summary: 'You explored all seven implemented components and database isolation. Lab figures include source documents; browser runs illustrate the algorithms on this device.',
  steps: [
    { id: 'hashing', route: '/system-design', target: 'lab-hashing', title: 'Move fewer cache keys', body: `Add a node to compute movement for the same generated keys with ring and modulo placement. Lab movement: ${measuredResults.hashing[0].value}.`, advanceOn: { type: 'manual' } },
    { id: 'limiter', route: '/system-design', target: 'lab-limiter', title: 'Enforce a shared budget', body: `Fire a burst to see actual accept and reject counts. After the tour, the controls let you explore Surge Mode. Lab admissions: ${measuredResults.limiter[0].value}. Class A remains finite.`, advanceOn: { type: 'manual' } },
    { id: 'links', route: '/system-design', target: 'lab-links', title: 'Unpredictable appointment links', body: `Generate random Base62, then inspect its stored digest. Adapter resolution p95: ${measuredResults.links[0].value}. No custom aliases or link cache.`, advanceOn: { type: 'manual' } },
    { id: 'autocomplete', route: '/system-design', target: 'lab-autocomplete', title: 'Measure before claiming a speedup', body: `Type a generated prefix to inspect its branch. After the tour, race trie against linear scan. Lab CPU means: ${measuredResults.autocomplete[0].value}; the lab baseline is sorted-prefix. Oversized indexes fall back.`, suggestion: 'doctor 00', advanceOn: { type: 'manual' } },
    { id: 'cache', route: '/system-design', target: 'lab-cache', title: 'Read, reuse, invalidate', body: `Read twice for a miss and a hit. Warm vs uncached lab p95: ${measuredResults.cache[0].value}. No mutex stampede lock was built.`, advanceOn: { type: 'manual' } },
    { id: 'snowflake', route: '/system-design', target: 'lab-snowflake', title: 'Ordered distributed IDs', body: `Generate IDs and check actual uniqueness and order. Lab result: ${measuredResults.snowflake[0].value}. The CSPRNG baseline was faster.`, advanceOn: { type: 'manual' } },
    { id: 'crawler', route: '/system-design', target: 'lab-crawler', title: 'Validate, dedupe, quarantine', body: `Fetch a fixture twice to see version-and-hash deduplication. After the tour, try a same-revision conflict. Lab result: ${measuredResults.crawler[0].value}; some pages failed. Only synthetic hosts are allowed.`, advanceOn: { type: 'manual' } },
    { id: 'isolation', route: '/system-design', target: 'lab-isolation', title: 'Independent ownership, connected workflows', body: `Try the illustrated cross-database join. ${measuredResults.isolation[0].value}; payment delivery uses an outbox and inbox, with acknowledgement after commit. This is isolation, not sharding.`, advanceOn: { type: 'manual' } },
  ],
};
