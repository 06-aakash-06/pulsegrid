export type TrafficClass = 'A' | 'B' | 'C';
export const surgeFactors = { A: 1, B: .6, C: .15 } as const;
export const surgeBudget = (budget: number, trafficClass: TrafficClass, surge: boolean) => budget * (surge ? surgeFactors[trafficClass] : 1);
export class TokenBucket {
  tokens: number;
  private last: number;
  constructor(readonly capacity: number, readonly refillPerSecond: number, now = performance.now()) {
    if (!Number.isFinite(capacity) || capacity <= 0 || !Number.isFinite(refillPerSecond) || refillPerSecond < 0) throw new Error('Use a positive capacity and nonnegative refill rate.');
    this.tokens = capacity; this.last = now;
  }
  refill(now = performance.now()) {
    this.tokens = Math.min(this.capacity, this.tokens + Math.max(0, now - this.last) / 1000 * this.refillPerSecond);
    this.last = Math.max(this.last, now);
  }
  accept(now = performance.now()): boolean {
    this.refill(now);
    if (this.tokens < 1) return false;
    this.tokens--; return true;
  }
  burst(count: number, now = performance.now()) {
    if (!Number.isInteger(count) || count < 0 || count > 100000) throw new Error('Burst must be between zero and one hundred thousand.');
    let accepted = 0;
    for (let i = 0; i < count; i++) if (this.accept(now)) accepted++;
    return { accepted, rejected: count - accepted };
  }
}
