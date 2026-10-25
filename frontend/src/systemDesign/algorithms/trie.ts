const normalize = (text: string) => text.normalize('NFKC').toLowerCase();
class Branch { children = new Map<string, Branch>(); words: string[] = []; }
export class Trie {
  private root = new Branch();
  constructor(words: string[]) {
    for (const word of [...new Set(words)].sort()) {
      let branch = this.root; branch.words.push(word);
      for (const char of normalize(word)) {
        if (!branch.children.has(char)) branch.children.set(char, new Branch());
        branch = branch.children.get(char)!; branch.words.push(word);
      }
    }
  }
  search(prefix: string, limit = 10): string[] {
    let branch = this.root;
    for (const char of normalize(prefix)) { const next = branch.children.get(char); if (!next) return []; branch = next; }
    return branch.words.slice(0, limit);
  }
}
export const linearScan = (words: string[], prefix: string, limit = 10) => [...new Set(words)].sort().filter(word => normalize(word).startsWith(normalize(prefix))).slice(0, limit);
export const generatedCatalog = (size = 10000) => Array.from({ length: size }, (_, i) => `${i % 2 ? 'doctor' : 'medicine'} ${String(i).padStart(5, '0')}`);
const median = (samples: number[]) => [...samples].sort((a, b) => a - b)[Math.floor(samples.length / 2)];
export function raceAutocomplete(words: string[], prefix: string, runs = 31, batch = 50) {
  const trie = new Trie(words);
  // Prepare both indexes before timing: the measured lab baseline is sorted-prefix,
  // while this explicitly labelled demonstration compares with a linear scan.
  const catalog = [...new Set(words)].sort();
  const normalized = normalize(prefix);
  const scan = () => catalog.filter(word => normalize(word).startsWith(normalized)).slice(0, 10);
  const trieSamples: number[] = [], scanSamples: number[] = [];
  let matches: string[] = [], checksum = 0;
  const timed = (fn: () => string[], samples: number[]) => {
    const start = performance.now();
    for (let j = 0; j < batch; j++) { matches = fn(); checksum += matches.length; }
    samples.push((performance.now() - start) / batch);
  };
  for (let i = 0; i < runs; i++) {
    if (i % 2) { timed(scan, scanSamples); timed(() => trie.search(prefix), trieSamples); }
    else { timed(() => trie.search(prefix), trieSamples); timed(scan, scanSamples); }
  }
  return { trieMs: median(trieSamples), scanMs: median(scanSamples), matches, runs, batch, checksum };
}
