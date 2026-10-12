"""Frozen v1 placement contract; no transport, health probing or replication."""
from bisect import bisect_left
from dataclasses import dataclass, field
from hashlib import sha256
import re

__all__ = ["Node", "RingSnapshot", "HashRing", "NoNodes", "InvalidTopology"]


class InvalidTopology(ValueError):
    """Invalid bounded configuration or topology transition."""


class NoNodes(InvalidTopology):
    """No logical nodes are available for placement."""


def _integer(value: int, low: int, high: int, name: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise InvalidTopology(f"{name} must be an integer in {low}..{high}")


@dataclass(frozen=True, slots=True)
class Node:
    node_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or re.fullmatch(
            r"[a-z][a-z0-9_-]{0,31}", self.node_id, flags=re.ASCII
        ) is None:
            raise InvalidTopology("node_id must match [a-z][a-z0-9_-]{0,31}")


@dataclass(frozen=True, slots=True)
class RingSnapshot:
    epoch: int
    virtual_nodes: int = 128
    node_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _integer(self.epoch, 1, 9007199254740991, "epoch")
        _integer(self.virtual_nodes, 1, 4096, "virtual_nodes")
        if type(self.node_ids) is not tuple or len(self.node_ids) > 32:
            raise InvalidTopology("node_ids must be a tuple with at most 32 nodes")
        for node_id in self.node_ids:
            Node(node_id)
        if len(set(self.node_ids)) != len(self.node_ids):
            raise InvalidTopology("duplicate node IDs")
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))


def _key_position(key: bytes) -> int:
    if not isinstance(key, bytes):
        raise TypeError("key must be bytes")
    return int.from_bytes(sha256(b"pg-ring-key-v1\0" + key).digest(), "big")


def _node_position(node_id: str, index: int) -> int:
    framed = b"pg-ring-node-v1\0" + node_id.encode("ascii") + b"\0" + str(index).encode("ascii")
    return int.from_bytes(sha256(framed).digest(), "big")


@dataclass(frozen=True, slots=True, init=False)
class HashRing:
    """Build O(NV log(NV)), locate O(log(NV)); updates return new rings.

    Each lookup retains a complete immutable ring. Publish a new ring/adapter
    under application synchronization; never mutate a live request's placement.
    """

    _snapshot: RingSnapshot
    _positions: tuple[int, ...] = field(repr=False)
    _owners: tuple[str, ...] = field(repr=False)

    def __init__(self, snapshot: RingSnapshot):
        if not isinstance(snapshot, RingSnapshot):
            raise InvalidTopology("snapshot must be RingSnapshot")
        if not snapshot.node_ids:
            raise NoNodes("empty topology")
        points = sorted(
            (_node_position(node_id, index), node_id, index)
            for node_id in snapshot.node_ids
            for index in range(snapshot.virtual_nodes)
        )
        object.__setattr__(self, "_snapshot", snapshot)
        object.__setattr__(self, "_positions", tuple(p[0] for p in points))
        object.__setattr__(self, "_owners", tuple(p[1] for p in points))

    @property
    def epoch(self) -> int:
        """Agent 3 structural Placement namespace generation."""
        return self._snapshot.epoch

    def locate(self, key: bytes) -> str:
        index = bisect_left(self._positions, _key_position(key))
        return self._owners[index % len(self._owners)]

    def snapshot(self) -> RingSnapshot:
        return self._snapshot

    def _next_snapshot(self, node_ids: tuple[str, ...], new_epoch: int) -> RingSnapshot:
        _integer(new_epoch, self.epoch + 1, 9007199254740991, "new_epoch")
        return RingSnapshot(new_epoch, self._snapshot.virtual_nodes, node_ids)

    def with_node(self, node: Node, new_epoch: int) -> "HashRing":
        if not isinstance(node, Node) or node.node_id in self._snapshot.node_ids:
            raise InvalidTopology("addition requires a new Node")
        return HashRing(self._next_snapshot(self._snapshot.node_ids + (node.node_id,), new_epoch))

    def without_node(self, node_id: str, new_epoch: int) -> "HashRing":
        Node(node_id)
        if node_id not in self._snapshot.node_ids:
            raise InvalidTopology("cannot remove absent node")
        return HashRing(self._next_snapshot(tuple(n for n in self._snapshot.node_ids if n != node_id), new_epoch))

    def health(self) -> dict[str, str | None]:
        """Configuration health only; does not establish Redis availability."""
        return {"state": "ok", "reason": None}
