# PulseGrid consistent hashing 1.0.0

Pure Python 3.11+ placement package, no runtime dependencies or Redis calls.
Exported frozen contract: `Node`, `RingSnapshot`, `HashRing`, `NoNodes`,
`InvalidTopology`; `HashRing.epoch` additionally satisfies Agent 3's structural
placement port. Importing this package performs no network/configuration work.

```python
from pulsegrid_consistent_hashing import HashRing, Node, RingSnapshot

ring = HashRing(RingSnapshot(epoch=1, node_ids=("cache_a", "cache_b")))
node_id = ring.locate(b"synthetic-directory-query-digest")
next_ring = ring.with_node(Node("cache_c"), new_epoch=2)
assert ring.epoch == 1  # original retained for in-flight operations
```

Defaults: 128 virtual nodes; allowed 1–4096; 1–32 logical nodes per ring.
Node IDs use `[a-z][a-z0-9_-]{0,31}`, with no address/credentials. Epochs are
positive JSON-safe integers and updates require a strictly larger epoch.
Snapshot node IDs are canonical sorted immutable tuples; duplicates rejected.
A snapshot may represent no nodes, but ring construction/last-node removal
raises `NoNodes` (a subtype of `InvalidTopology`), so no usable empty ring exists.
An absent removal, duplicate addition, bad configuration or nonincreasing epoch
raises `InvalidTopology`; nonbytes lookup keys raise `TypeError`.

Key position: full unsigned big-endian SHA256 of `b"pg-ring-key-v1\0" + key`.
Point position: SHA256 of `b"pg-ring-node-v1\0" + node_id_ascii + b"\0" +
index_decimal_ascii`. Points sort by `(position, node_id, index)`, and lookup
chooses the first position at least the key position, wrapping at the end.
Colliding positions retain every vnode; the lexical first node wins that exact
boundary. Collisions can worsen balance; they do not produce ambiguous placement.
No Python randomized hashes or health-based rerouting. Build time O(NV log(NV)),
retained memory O(NV), lookup O(log(NV)) plus key hashing. Updates build new rings;
all reads and snapshots are immutable and require no mutation locks.

`health()` is synchronous configuration health, returning `{state: "ok",
reason: None}`. It provides no assertion about a Redis endpoint's health.
Metrics are measured by the owned benchmark; the frozen constructor accepts only
a snapshot, so coordinator observers may wrap locate/build without importing
business models or adding keys/identities to labels.

From repository root, without package installation:

```sh
PYTHONPATH=components/consistent_hashing python3 -m unittest discover -s components/consistent_hashing/tests -v
python3 -m compileall -q components/consistent_hashing experiments/phase4/consistent_hashing
```

Golden fixture values are generated independently from the byte specification
and checked against the implementation; tests force otherwise impractical hash
collisions. Subprocess tests change PYTHONHASHSEED. See [integration guide](INTEGRATION.md),
[handoff](HANDOFF.md) and [benchmark guide](../../experiments/phase4/consistent_hashing/README.md).
