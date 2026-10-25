import { render, screen, within, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { LabCard } from '../src/systemDesign/LabCard';
import { measuredResults, type LabTopic } from '../src/systemDesign/measuredResults';
import { systemDesignTour } from '../src/simulation/tours/systemDesign';
afterEach(cleanup);
it('renders every measured number exclusively from the central registry with document source links', () => {
  const topics = Object.keys(measuredResults) as LabTopic[];
  render(<MemoryRouter>{topics.map(topic => <LabCard key={topic} topic={topic} title={topic} purpose="Purpose" screen="Screen" href="/patient/doctors" why="Trade-off"><p>Browser result stays outside the measured section.</p></LabCard>)}</MemoryRouter>);
  for (const topic of topics) {
    const evidence = screen.getByRole('region', { name: `${topic} lab evidence` });
    const values = [...evidence.querySelectorAll('[data-measured-value]')].map(node => node.getAttribute('data-measured-value'));
    expect(values).toEqual(measuredResults[topic].map(figure => figure.value));
    expect(evidence.textContent).not.toContain('Browser result');
    expect(within(evidence).getAllByRole('link')).toHaveLength(measuredResults[topic].length);
    for (const figure of measuredResults[topic]) {
      expect(existsSync(resolve(__dirname, '../..', figure.source))).toBe(true);
      expect(within(evidence).getByText(figure.value)).toBeInTheDocument();
      expect(evidence.textContent).toContain(figure.source);
    }
  }
  // Widgets cannot own another measured block or copy lab figures into prose.
  const directory = resolve(__dirname, '../src/systemDesign');
  for (const name of readdirSync(directory).filter(file => file.endsWith('.tsx') && file !== 'LabCard.tsx')) {
    const source = readFileSync(resolve(directory, name), 'utf8');
    expect(source).not.toMatch(/data-measured-value|className="lab-measured"|Measured in our lab/);
    for (const figures of Object.values(measuredResults)) for (const figure of figures) expect(source).not.toContain(figure.value);
  }
});
it('registers one source-backed step for every card without requesting server writes', () => {
  expect(systemDesignTour.role).toBeNull();
  expect(systemDesignTour.steps).toHaveLength(Object.keys(measuredResults).length);
  expect(systemDesignTour.steps.every(step => step.route === '/system-design' && !step.mutates)).toBe(true);
});
