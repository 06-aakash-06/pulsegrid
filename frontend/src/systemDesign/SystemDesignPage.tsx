import { HospitalHeader } from '../design/HospitalHeader';
import { PageHeader } from '../components/PageHeader';
import { PageGrid } from '../components/PageGrid';
import { useSimulation } from '../simulation/SimulationProvider';
import { systemDesignTour } from '../simulation/tours/systemDesign';
import { LabCard } from './LabCard';
import { HashingDemo } from './HashingDemo';
import { LimiterDemo } from './LimiterDemo';
import { AutocompleteDemo } from './AutocompleteDemo';
import { SnowflakeDemo } from './SnowflakeDemo';
import { ShortLinkDemo, CacheDemo, CrawlerDemo, IsolationDemo } from './SupportingDemos';
import './systemDesign.css';
export function SystemDesignPage() {
  const simulation = useSimulation();
  return <div className="workspace-shell environment-control system-design-shell"><HospitalHeader /><main className="workspace-content system-design-lab" id="system-design-main">
    <PageHeader department="control" title="System Design Lab: the 7 components behind PulseGrid" subtitle="Run the algorithms. Inspect the evidence. Understand the trade-offs." actions={<button onClick={() => simulation?.start(systemDesignTour, false)}>Run guided tour</button>} />
    <p className="lab-intro">Seven algorithms and infrastructure components, plus the database ownership boundary they work inside. Browser experiments are illustrative; lab evidence below records the measured workload and its limits.</p>
    <PageGrid className="lab-grid">
      <LabCard topic="hashing" title="Consistent hashing" purpose="Spreads the doctor cache across Redis nodes so adding one moves fewer keys." screen="Consultation search" href="/patient/doctors" why="Modulo is cheaper per lookup but moves more keys when the node count changes."><HashingDemo /></LabCard>
      <LabCard topic="limiter" title="Rate limiter + Surge Mode" purpose="Shares admission budgets across replicas and protects critical workflows during pressure." screen="Control Room" href="/ops/dashboard" why="A process-local limiter multiplies a shared quota across replicas; coordination costs latency."><LimiterDemo /></LabCard>
      <LabCard topic="links" title="URL shortener" purpose="Issues revocable, scoped appointment capabilities with unpredictable tokens." screen="Appointments" href="/patient/appointments" why="Sequential IDs are guessable; random tokens reduce enumeration, while authorization still controls access."><ShortLinkDemo /></LabCard>
      <LabCard topic="autocomplete" title="Autocomplete" purpose="Finds doctor and medicine prefixes through bounded owner-local indexes." screen="Consultation search" href="/patient/doctors" why="A trie is an experiment in indexing, not a proven speed win here; oversized catalogs fall back to the owner database."><AutocompleteDemo /></LabCard>
      <LabCard topic="cache" title="Key-value cache" purpose="Serves repeated directory reads while preserving database authority on misses and outages." screen="Consultation search" href="/patient/doctors" why="Repeated database reads cost more under the measured high load; TTL and invalidation trade freshness for reuse."><CacheDemo /></LabCard>
      <LabCard topic="snowflake" title="Snowflake IDs" purpose="Allocates ordered, distributed identifiers within explicitly assigned service and replica partitions." screen="Appointment identifiers" href="/patient/appointments" why="CSPRNG was faster in our lab; Snowflake adds ordering and explicit worker identity, with durable reservation complexity."><SnowflakeDemo /></LabCard>
      <LabCard topic="crawler" title="Web crawler" purpose="Refreshes synthetic insurance rules with provenance and rejects conflicting revisions." screen="Insurance estimates" href="/billing/insurance" why="Blind overwrites conceal source conflicts; version and hash validation preserve trustworthy estimates."><CrawlerDemo /></LabCard>
      <LabCard topic="isolation" title="Database per service (isolation)" purpose="Keeps each domain’s writes, schema and credentials inside its ownership boundary." screen="Control Room event delivery" href="/admin/control-room" why="Shared tables simplify joins but couple domains; owner APIs and outbox/inbox delivery preserve independent transactions."><IsolationDemo /></LabCard>
    </PageGrid>
  </main></div>;
}
