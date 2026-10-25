import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ShortLinkDemo, CacheDemo, CrawlerDemo, IsolationDemo } from '../src/systemDesign/SupportingDemos';
import { LimiterDemo } from '../src/systemDesign/LimiterDemo';
import { SnowflakeDemo } from '../src/systemDesign/SnowflakeDemo';
import { AutocompleteDemo } from '../src/systemDesign/AutocompleteDemo';
const mocks = vi.hoisted(() => ({ request: vi.fn(), metadata: vi.fn() }));
vi.mock('../src/auth/authContext', () => ({ useAuth: () => ({ state: { status: 'authenticated', roleHints: ['patient'] }, api: { request: mocks.request, requestWithMetadata: mocks.metadata } }) }));
vi.mock('../src/simulation/SimulationProvider', () => ({ useSimulation: () => ({ sampleBackend: true }) }));
afterEach(() => vi.resetAllMocks());
it('fires actual bursts and scales the C budget during surge', () => {
  render(<LimiterDemo />);
  fireEvent.click(screen.getByRole('button', { name: 'Fire burst' }));
  expect(screen.getByRole('status')).toHaveTextContent('Accepted 60 · rejected 100');
  fireEvent.click(screen.getByRole('checkbox', { name: 'Surge Mode' }));
  fireEvent.click(screen.getByRole('button', { name: 'Fire burst' }));
  expect(screen.getByRole('status')).toHaveTextContent('Accepted 9 · rejected 151');
});
it('shows actual cache misses, hits and invalidation', () => {
  render(<CacheDemo />);
  fireEvent.click(screen.getByRole('button', { name: 'Read directory' }));
  expect(screen.getByRole('status')).toHaveTextContent('MISS');
  fireEvent.click(screen.getByRole('button', { name: 'Read directory' }));
  expect(screen.getByRole('status')).toHaveTextContent('HIT');
  fireEvent.click(screen.getByRole('button', { name: 'Invalidate cache' }));
  fireEvent.click(screen.getByRole('button', { name: 'Read directory' }));
  expect(screen.getByRole('status')).toHaveTextContent('MISS');
});
it('blocks the illustrative join without making any API request', () => {
  render(<IsolationDemo />);
  fireEvent.click(screen.getByRole('button', { name: 'Try cross-database join' }));
  expect(screen.getByRole('status')).toHaveTextContent('outbox');
  expect(mocks.request).not.toHaveBeenCalled();
});
it('creates a real link with the owner ETag, correct purpose and idempotency', async () => {
  mocks.metadata.mockResolvedValue({ data: { version: 3 }, etag: '"3"' });
  mocks.request.mockResolvedValue({ short_path: '/s/synthetic', expires_at: '2026-10-26T12:00:00Z' });
  render(<ShortLinkDemo />);
  fireEvent.change(screen.getByLabelText('Owned appointment ID'), { target: { value: '5112' } });
  fireEvent.click(screen.getByRole('button', { name: 'Call the real service · create link' }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('/api/v1/appointments/5112/short-links', expect.objectContaining({ method: 'POST', body: { purpose: 'appointment' }, ifMatch: '"3"', idempotencyKey: expect.any(String) })));
  expect(await screen.findByText(/Owner created/)).toHaveTextContent('/s/synthetic');
});
it('quarantines a real computed fixture conflict', async () => {
  render(<CrawlerDemo />);
  fireEvent.click(screen.getByRole('button', { name: 'Try revision conflict' }));
  await waitFor(() => expect(screen.getByRole('log')).toHaveTextContent('QUARANTINE'));
  fireEvent.click(screen.getByRole('button', { name: 'Publish next revision' }));
  await waitFor(() => expect(screen.getByRole('log').textContent?.trim().endsWith('ESTIMATE ready with source-run provenance')).toBe(true));
});
it('checks uniqueness and ordering of generated Snowflakes', async () => {
  render(<SnowflakeDemo />);
  fireEvent.click(screen.getByRole('button', { name: 'Generate 10,000 IDs' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('10,000 generated · 0 collisions · strictly increasing: yes'));
});
it('times both searches and calls the autocomplete owner endpoint', async () => {
  mocks.request.mockResolvedValue({ items: [] });
  render(<AutocompleteDemo />);
  fireEvent.click(screen.getByRole('button', { name: 'Race trie vs linear scan' }));
  await waitFor(() => expect(screen.getAllByRole('status')[0]).toHaveTextContent('Median per lookup: trie'));
  fireEvent.click(screen.getByRole('button', { name: 'Call the real service · medicines' }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('/api/v1/pharmacy/medicines/autocomplete?prefix=doctor%2000&limit=10'));
  expect(screen.getAllByText(/Connected to dev\/demo mock API/)).toHaveLength(2);
});
