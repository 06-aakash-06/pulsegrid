export type TrafficClass = 'A' | 'B' | 'C';
export const surgeFactors = { A: 1, B: .6, C: .15 } as const;
/** Single-replica floor from policies.py. Refill budgets are passed in milli-tokens. */
export function surgeBudget(budget: number, trafficClass: TrafficClass, surge: boolean) {
  if (!Number.isInteger(budget) || budget < 1) throw new Error('Budget must be a positive integer.');
  return Math.min(budget, Math.max(1, Math.floor(budget * (surge ? surgeFactors[trafficClass] : 1))));
}
/** Fixed-point token accounting ported from bucket.lua; this model has one bucket. */
export class TokenBucket {
  private milliTokens: number;
  private carry = 0;
  private last: number;
  private readonly rate: number;
  get tokens() { return this.milliTokens / 1000; }
  constructor(readonly capacity: number, readonly refillPerSecond: number, now = performance.now()) {
    if (!Number.isInteger(capacity) || capacity < 1 || capacity > 100000 || !Number.isFinite(refillPerSecond) || refillPerSecond < .001 || refillPerSecond > 100000) throw new Error('Use a whole positive capacity and refill between .001 and one hundred thousand.');
    this.milliTokens = capacity * 1000; this.rate = Math.round(refillPerSecond * 1000); this.last = Math.floor(now);
  }
  refill(now = performance.now()) {
    const time = Math.floor(now), cap = this.capacity * 1000;
    const elapsed = Math.min(Math.ceil(cap * 1000 / this.rate), Math.max(0, time - this.last));
    const credit = elapsed * this.rate + this.carry;
    this.milliTokens = Math.min(cap, this.milliTokens + Math.floor(credit / 1000));
    this.carry = this.milliTokens === cap ? 0 : credit % 1000;
    this.last = Math.max(this.last, time);
  }
  accept(now = performance.now()): boolean {
    this.refill(now);
    if (this.milliTokens < 1000) return false;
    this.milliTokens -= 1000; return true;
  }
  burst(count: number, now = performance.now()) {
    if (!Number.isInteger(count) || count < 0 || count > 100000) throw new Error('Burst must be between zero and one hundred thousand.');
    let accepted = 0;
    for (let i = 0; i < count; i++) if (this.accept(now)) accepted++;
    return { accepted, rejected: count - accepted };
  }
}
