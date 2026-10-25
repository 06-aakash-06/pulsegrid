import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { measuredResults, type LabTopic } from './measuredResults';
import phase4 from '../../../docs/phase-4-integration-verification.md?url';
import phase6 from '../../../docs/phase-6-integration-verification.md?url';
import phase82 from '../../../docs/phase-8-2-scalability-finalization.md?url';
const sources: Record<string, string> = {
  'docs/phase-4-integration-verification.md': phase4,
  'docs/phase-6-integration-verification.md': phase6,
  'docs/phase-8-2-scalability-finalization.md': phase82,
};
export function LabCard({ topic, title, purpose, screen, href, why, children }: {
  topic: LabTopic; title: string; purpose: string; screen: string; href: string; why: string; children: ReactNode;
}) {
  return <article className="lab-card" aria-labelledby={`lab-${topic}`}>
    <header><span className="lab-eyebrow">Explore the architecture</span><h2 id={`lab-${topic}`}>{title}</h2><p>{purpose}</p>
      <p className="lab-used">Where it’s used: <Link to={href}>{screen} →</Link><small>Workspace permissions apply</small></p></header>
    <section className="lab-demo" aria-label={`${title} browser demo`}><h3>Live in your browser (illustrative)</h3>{children}</section>
    <section className="lab-measured" data-lab-topic={topic} aria-label={`${title} lab evidence`}><h3>Measured in our lab</h3>
      {measuredResults[topic].map(figure => <div className="lab-figure" key={figure.value} data-measured-value={figure.value}>
        <strong>{figure.value}</strong><p>{figure.label}</p>
        <a href={sources[figure.source]} target="_blank" rel="noreferrer" title={figure.source}>Measured in our lab · source <span className="lab-source-path">{figure.source}</span></a>
      </div>)}
    </section><footer><h3>Why not the simple option?</h3><p>{why}</p></footer>
  </article>;
}
