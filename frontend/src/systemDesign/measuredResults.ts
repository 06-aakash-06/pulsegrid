/** Only lab evidence lives here. Browser outputs never enter this registry.
 * Wording preserves workload, baseline and known limitations of the source. */
const phase4 = 'docs/phase-4-integration-verification.md';
const phase6 = 'docs/phase-6-integration-verification.md';
const phase82 = 'docs/phase-8-2-scalability-finalization.md';
export interface LabFigure { value: string; label: string; source: string; anchor: string }
export const measuredResults = {
  hashing: [
    { value: '25.43–25.50% vs 74.97–75.12%', label: 'Ring vs modulo movement · one million keys, three to four nodes', source: phase4, anchor: '4-component-measurements' },
    { value: '28.56% vs 67.31%', label: 'Live Redis topology · ten thousand keys, two to three nodes', source: phase4, anchor: '4-component-measurements' },
  ],
  limiter: [
    { value: '60/160 vs 120/160', label: 'Shared Redis admissions vs process-local baseline · shared budget sixty', source: phase4, anchor: '4-component-measurements' },
    { value: '6.725–7.722 ms', label: 'Redis decision p95 · coordination has a cost', source: phase4, anchor: '4-component-measurements' },
    { value: '63 admitted · 37 limited', label: 'Live gateway · one hundred authenticated searches', source: phase4, anchor: '4-component-measurements' },
    { value: 'A 100% · B 60% · C 15%', label: 'Implemented SURGE owner-budget profile, not a timing measurement', source: phase6, anchor: 'surge-mode-and-operation-classes' },
  ],
  links: [
    { value: '118.03–128.89 ms', label: 'Adapter resolution p95 · thirty-two clients; fake authorization/effect ports', source: phase4, anchor: '4-component-measurements' },
    { value: '32,935 resolutions · zero errors', label: 'Post-fix adapter workload; authenticated high-concurrency endpoint acceptance remains partial', source: phase4, anchor: '4-component-measurements' },
  ],
  autocomplete: [
    { value: '0.0025 ms vs 0.0025 ms', label: 'Doctor high CPU mean · trie vs sorted-prefix baseline, not SQL', source: phase4, anchor: '4-component-measurements' },
    { value: '123.03 MiB > 64 MiB', label: 'Doctor trie estimate at one hundred thousand entries → database fallback', source: phase4, anchor: '4-component-measurements' },
  ],
  cache: [
    { value: '15.836 ms vs 36.418 ms', label: 'High-load p95 · warm cache vs uncached', source: phase4, anchor: '4-component-measurements' },
    { value: '2,535.1 vs 1,754.9 reads/s', label: 'High-load warm vs uncached · means across three trials', source: phase4, anchor: '4-component-measurements' },
  ],
  snowflake: [
    { value: '4.5 million · zero collisions', label: 'Snowflake allocations/inserts across benchmark levels', source: phase4, anchor: '4-component-measurements' },
    { value: '10,449–10,849 IDs/s', label: 'Medium-load Snowflake pipeline', source: phase4, anchor: '4-component-measurements' },
    { value: '1.806× faster CSPRNG', label: 'Medium-load baseline mean throughput; no Snowflake speed win', source: phase4, anchor: '4-component-measurements' },
  ],
  crawler: [
    { value: '52.38 pages/s · 100% accuracy', label: 'Synthetic crawler high workload · eight slots; extraction/rule correctness', source: phase4, anchor: '4-component-measurements' },
    { value: '293/300 pages · seven failures', label: 'High workload; eight invalid pages rejected separately · fake persistence port', source: phase4, anchor: '4-component-measurements' },
  ],
  isolation: [
    { value: 'Seven owner databases', label: 'Verified architecture; isolation is not a latency benchmark', source: phase6, anchor: 'architecture-and-scope' },
    { value: 'One matching inbox row · attempt 2', label: 'Payment outbox replay after broker recovery; at-least-once delivery', source: phase6, anchor: 'live-failure-recovery-and-workflow-results' },
    { value: '126.33 → 245.33 requests/s', label: 'Doctor replicas one to two · sixteen clients; service scaling, not sharding', source: phase82, anchor: '7-replica-scaling' },
  ],
} satisfies Record<string, LabFigure[]>;
export type LabTopic = keyof typeof measuredResults;
