// Port of components/consistent_hashing: full SHA-256, domain framing, bisect-left.
export const VIRTUAL_NODES = 128;
export const HASH_SPACE = 1n << 256n;
export async function sha256(value: string): Promise<bigint> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return BigInt('0x' + Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join(''));
}
export const hashKey = (key: string) => sha256(`pg-ring-key-v1\0${key}`);
export interface RingPoint { position: bigint; node: string }
export class HashRing {
  readonly nodes: string[];
  constructor(readonly points: RingPoint[]) {
    this.points = [...points].sort((a, b) => a.position < b.position ? -1 : a.position > b.position ? 1 : a.node.localeCompare(b.node));
    this.nodes = [...new Set(points.map(p => p.node))].sort();
  }
  static async create(nodes: string[]): Promise<HashRing> {
    if (new Set(nodes).size !== nodes.length) throw new Error('Nodes must be unique.');
    const points = await Promise.all(nodes.flatMap(node => Array.from({ length: VIRTUAL_NODES }, async (_, i) => ({ node, position: await sha256(`pg-ring-node-v1\0${node}\0${i}`) }))));
    return new HashRing(points);
  }
  locate(position: bigint): string {
    if (!this.points.length) throw new Error('The ring needs a node.');
    let low = 0, high = this.points.length;
    while (low < high) { const mid = (low + high) >>> 1; if (this.points[mid].position < position) low = mid + 1; else high = mid; }
    return this.points[low % this.points.length].node;
  }
}
export function comparePlacement(before: HashRing, after: HashRing, keys: bigint[]) {
  let ringMoved = 0, moduloMoved = 0;
  for (const key of keys) {
    if (before.locate(key) !== after.locate(key)) ringMoved++;
    if (before.nodes[Number(key % BigInt(before.nodes.length))] !== after.nodes[Number(key % BigInt(after.nodes.length))]) moduloMoved++;
  }
  return { ringMoved, moduloMoved, total: keys.length };
}
