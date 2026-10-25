/** Local TTL teaching model; deliberately no distributed lock/stampede claim. */
export class DemoCache {
  private entries = new Map<string, { value: string; expires: number }>();
  read(key: string, now = performance.now()) {
    const entry = this.entries.get(key);
    if (entry && entry.expires > now) return { value: entry.value, hit: true };
    const value = `Synthetic directory result for ${key}`;
    this.entries.set(key, { value, expires: now + 10000 });
    return { value, hit: false };
  }
  invalidate() { this.entries.clear(); }
}
