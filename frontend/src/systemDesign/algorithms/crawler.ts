import { sha256 } from './hashRing';
export interface Fixture { host: string; version: number; content: string }
export class FixtureCrawler {
  private revisions = new Map<number, bigint>();
  quarantined = false;
  async ingest(page: Fixture): Promise<string[]> {
    if (page.host !== 'synthetic-provider.fixture') return ['BLOCK host outside synthetic allowlist'];
    const log = [`FETCH ${page.host}`, 'VALIDATE bounded synthetic provider record'];
    if (!Number.isInteger(page.version) || page.version < 1 || !page.content.startsWith('coverage:')) return [...log, 'REJECT invalid fixture'];
    const hash = await sha256(page.content);
    const known = this.revisions.get(page.version);
    if (known === hash) return [...log, 'DEDUPE version + content hash: unchanged'];
    if (known !== undefined) { this.quarantined = true; return [...log, 'QUARANTINE same-revision content conflict', 'ESTIMATE blocked: source conflict']; }
    if (this.revisions.size && page.version < Math.max(...this.revisions.keys())) return [...log, 'REJECT stale revision'];
    this.revisions.set(page.version, hash); this.quarantined = false;
    return [...log, 'DEDUPE new version + content hash: stored', 'ESTIMATE ready with source-run provenance'];
  }
}
