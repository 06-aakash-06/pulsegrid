# PulseGrid autocomplete component

`pulsegrid-autocomplete` is a dependency-free Python package for Doctor and
Pharmacy owner adapters. It implements Unicode NFKC/casefold/whitespace prefix
normalization, deterministic top-K radix-trie search, duplicate identity
suppression, rename/removal updates, immutable revision-tagged snapshots, and
revision-checked atomic index refresh.

The package returns only source IDs, kinds, and display labels. Each owner
adapter independently enforces existing authenticated directory/catalog access,
revalidates selected IDs against its current owner database snapshot, and falls
back to its owner DB query when the index is unavailable or invalid. It is not a
service, database model, authorization authority, or cache of Pharmacy stock.

Default snapshot admission is 100,000 entries and an approximate 64 MiB retained
object estimate; configure `IndexLimits` through the owner ports. Searches
support a configurable 1–20 result limit (default 10). Published snapshots are
read-only. See [HANDOFF.md](HANDOFF.md) for route, migration, refresh, metrics,
and owner integration instructions, and
[`experiments/phase4/autocomplete/README.md`](../../experiments/phase4/autocomplete/README.md)
for benchmark commands and limits.
