import { describe, expect, it } from 'vitest';
import { HashRing, hashKey, comparePlacement } from '../src/systemDesign/algorithms/hashRing';
import { TokenBucket, surgeBudget } from '../src/systemDesign/algorithms/tokenBucket';
import { Snowflake, EPOCH, decodeSnowflake } from '../src/systemDesign/algorithms/snowflake';
import { Trie, linearScan, raceAutocomplete } from '../src/systemDesign/algorithms/trie';

describe('browser algorithms', () => {
  it('uses clockwise SHA-256 placement and moves about the new node share', async () => {
    const old = await HashRing.create(['redis_a', 'redis_b', 'redis_c']);
    const next = await HashRing.create(['redis_a', 'redis_b', 'redis_c', 'redis_d']);
    const keys = await Promise.all(Array.from({ length: 10000 }, (_, i) => hashKey(`synthetic-${i}`)));
    const result = comparePlacement(old, next, keys);
    expect(result.ringMoved / keys.length).toBeGreaterThan(.18);
    expect(result.ringMoved / keys.length).toBeLessThan(.32);
    expect(result.moduloMoved / keys.length).toBeGreaterThan(.70);
    for (const key of keys.slice(0, 100)) if (old.locate(key) !== next.locate(key)) expect(next.locate(key)).toBe('redis_d');
    expect(await HashRing.create([])).toBeDefined();
    expect(() => new HashRing([]).locate(0n)).toThrow();
    const removed = await HashRing.create(['redis_a', 'redis_b']);
    for (const key of keys.slice(0, 100)) if (old.locate(key) !== 'redis_c') expect(removed.locate(key)).toBe(old.locate(key));
  });
  it('admits exactly capacity, refills and applies actual class budgets', () => {
    const bucket = new TokenBucket(60, 10, 0);
    expect(bucket.burst(160, 0)).toEqual({ accepted: 60, rejected: 100 });
    expect(bucket.burst(12, 1000)).toEqual({ accepted: 10, rejected: 2 });
    expect(bucket.burst(100, 100000)).toEqual({ accepted: 60, rejected: 40 });
    expect(surgeBudget(100, 'A', true)).toBe(100);
    expect(surgeBudget(100, 'B', true)).toBe(60);
    expect(surgeBudget(100, 'C', true)).toBe(15);
    expect(surgeBudget(1, 'C', true)).toBe(1);
    const fractional = new TokenBucket(1, .001, 0);
    expect(fractional.accept(0)).toBe(true);
    expect(fractional.accept(999999)).toBe(false);
    expect(fractional.accept(1000000)).toBe(true);
    expect(() => new TokenBucket(-1, 1)).toThrow();
    expect(() => bucket.burst(-1)).toThrow();
  });
  it('generates 10k unique monotonic IDs with real worker layout and overflow', () => {
    const generator = new Snowflake(3, 2);
    const ids = Array.from({ length: 10000 }, (_, i) => generator.next(EPOCH + 100 + Math.floor(i / 4096)));
    expect(new Set(ids).size).toBe(10000);
    expect(ids.every((id, i) => i === 0 || id > ids[i - 1])).toBe(true);
    expect(decodeSnowflake(ids[0]).worker).toBe((3 << 7) | 2);
    expect(decodeSnowflake(ids[4096]).time).toBe(101n);
    expect(() => generator.next(EPOCH + 99)).toThrow(/backward/);
    expect(() => new Snowflake(7, 0)).toThrow();
    const full = new Snowflake(1, 0);
    for (let i = 0; i < 4096; i++) full.next(EPOCH + 1);
    expect(() => full.next(EPOCH + 1)).toThrow(/Sequence exhausted/);
    expect(full.next(EPOCH + 2)).toBeGreaterThan(0n);
    expect(() => new Snowflake(0, 128)).toThrow();
  });
  it('matches scan including empty, missing and case-normalized prefixes', () => {
    const words = ['doctor zoe', 'doctor ada', 'doctor ada', 'medicine a', 'DOVE'];
    const trie = new Trie(words);
    for (const prefix of ['', 'do', 'DO', 'doctor a', 'missing']) expect(trie.search(prefix)).toEqual(linearScan(words, prefix));
    const race = raceAutocomplete(words, 'do');
    expect(race.matches).toEqual(trie.search('do'));
    expect(race.trieMs).toBeGreaterThanOrEqual(0);
    expect(race.scanMs).toBeGreaterThanOrEqual(0);
  });
});

import { DemoCache } from '../src/systemDesign/algorithms/cache';
import { FixtureCrawler } from '../src/systemDesign/algorithms/crawler';
import { createShortToken } from '../src/systemDesign/algorithms/shortLink';
it('creates fixed-width random Base62 and stores a digest, not a sequential alias', async () => {
  const a = await createShortToken(), b = await createShortToken();
  expect(a.token).toMatch(/^[0-9A-Za-z]{22}$/);
  expect(a.hash).toMatch(/^[0-9a-f]{64}$/);
  expect(a.token).not.toBe(b.token);
});
it('expires and invalidates local cached results', () => {
  const cache = new DemoCache();
  expect(cache.read('a', 0).hit).toBe(false);
  expect(cache.read('a', 1).hit).toBe(true);
  expect(cache.read('a', 10001).hit).toBe(false);
  cache.invalidate(); expect(cache.read('a', 10002).hit).toBe(false);
});
it('validates allowlisted fixtures, deduplicates, quarantines and recovers on a newer revision', async () => {
  const crawler = new FixtureCrawler();
  const fixture = { host: 'synthetic-provider.fixture', version: 1, content: 'coverage:80' };
  expect((await crawler.ingest({ ...fixture, host: 'external.test' })).join()).toContain('BLOCK');
  expect((await crawler.ingest({ ...fixture, content: 'bad' })).join()).toContain('REJECT');
  expect((await crawler.ingest(fixture)).join()).toContain('ESTIMATE ready');
  expect((await crawler.ingest(fixture)).join()).toContain('unchanged');
  expect((await crawler.ingest({ ...fixture, content: 'coverage:90' })).join()).toContain('QUARANTINE');
  expect(crawler.quarantined).toBe(true);
  expect((await crawler.ingest({ ...fixture, version: 2 })).join()).toContain('ESTIMATE ready');
  expect(crawler.quarantined).toBe(false);
  expect((await crawler.ingest({ ...fixture, version: 1, content: 'coverage:70' })).join()).toContain('QUARANTINE');
});
