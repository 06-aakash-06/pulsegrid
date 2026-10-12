import concurrent.futures
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from pulsegrid_consistent_hashing import HashRing, InvalidTopology, Node, NoNodes, RingSnapshot


# Independent direct implementation of the frozen byte framing, not ring internals.
def oracle(key, nodes, vnodes):
    target = int(hashlib.sha256(b"pg-ring-key-v1\0" + key).hexdigest(), 16)
    points = sorted((int(hashlib.sha256(b"pg-ring-node-v1\0" + n.encode() + b"\0" + str(i).encode()).hexdigest(), 16), n, i)
                    for n in nodes for i in range(vnodes))
    return next((n for p, n, _ in points if p >= target), points[0][1])


class RingTests(unittest.TestCase):
    def setUp(self):
        self.ring = HashRing(RingSnapshot(1, 128, ("redis_c", "redis_a", "redis_b")))
        self.keys = [f"synthetic-{i}".encode() for i in range(10000)]

    def test_golden_vectors(self):
        vectors = json.loads(Path(__file__).with_name("golden_vectors.json").read_text())
        for vector in vectors:
            ring = HashRing(RingSnapshot(1, vector["vnodes"], tuple(vector["nodes"])))
            key = bytes.fromhex(vector["key_hex"])
            self.assertEqual(oracle(key, vector["nodes"], vector["vnodes"]), vector["owner"])
            self.assertEqual(ring.locate(key), vector["owner"])

    def test_independent_processes(self):
        script = "from pulsegrid_consistent_hashing import *; import json; r=HashRing(RingSnapshot(1,128,('redis_c','redis_b','redis_a'))); print(json.dumps([r.locate(str(i).encode()) for i in range(1000)]))"
        expected = [self.ring.locate(str(i).encode()) for i in range(1000)]
        for salt in ("1", "999", "random"):
            result = subprocess.check_output([sys.executable, "-c", script], env={**os.environ, "PYTHONHASHSEED": salt}, text=True)
            self.assertEqual(json.loads(result), expected)

    def test_snapshot_order_and_epoch(self):
        other = HashRing(RingSnapshot(99, 128, ("redis_b", "redis_c", "redis_a")))
        self.assertEqual(other.snapshot().node_ids, ("redis_a", "redis_b", "redis_c"))
        self.assertEqual([other.locate(k) for k in self.keys], [self.ring.locate(k) for k in self.keys])
        with self.assertRaises(FrozenInstanceError):
            self.ring._owners = ()
        with self.assertRaises(FrozenInstanceError):
            other.snapshot().epoch = 2
        self.assertEqual(other.epoch, 99)

    def test_virtual_nodes(self):
        for count in (1, 32, 128, 512, 4096):
            ring = HashRing(RingSnapshot(1, count, ("a", "b")))
            self.assertEqual(len(ring._positions), 2 * count)
            for key in (b"", b"x", b"\xff\0"):
                self.assertEqual(ring.locate(key), oracle(key, ("a", "b"), count))

    def test_collisions_and_boundaries(self):
        with patch("pulsegrid_consistent_hashing._node_position", return_value=7):
            ring = HashRing(RingSnapshot(1, 3, ("b", "a")))
            self.assertEqual(ring._owners, ("a", "a", "a", "b", "b", "b"))
            for key_position in (0, 7, 8, 2**256 - 1):
                with patch("pulsegrid_consistent_hashing._key_position", return_value=key_position):
                    self.assertEqual(ring.locate(b"key"), "a")
        with patch("pulsegrid_consistent_hashing._node_position", side_effect=lambda n, i: {"a": 10, "b": 20}[n]):
            ring = HashRing(RingSnapshot(1, 1, ("b", "a")))
            for position, expected in ((0, "a"), (10, "a"), (11, "b"), (20, "b"), (21, "a")):
                with patch("pulsegrid_consistent_hashing._key_position", return_value=position):
                    self.assertEqual(ring.locate(b"key"), expected)

    def test_add_remove_movement(self):
        added = self.ring.with_node(Node("redis_d"), 2)
        removed = added.without_node("redis_b", 3)
        added_moves = removed_moves = 0
        for key in self.keys:
            before, after, final = self.ring.locate(key), added.locate(key), removed.locate(key)
            if before != after:
                added_moves += 1
                self.assertEqual(after, "redis_d")
            if after != final:
                removed_moves += 1
                self.assertEqual(after, "redis_b")
        self.assertTrue(0 < added_moves < len(self.keys))
        self.assertTrue(0 < removed_moves < len(self.keys))
        self.assertEqual(self.ring.epoch, 1)
        self.assertEqual(added.epoch, 2)

    def test_invalid_topologies(self):
        for node_id in ("", "A", "1", "a.b", "é", "a" * 33, None, 1):
            with self.assertRaises(InvalidTopology):
                Node(node_id)
        for count in (0, 4097, True, 1.2):
            with self.assertRaises(InvalidTopology):
                RingSnapshot(1, count, ("a",))
        for epoch in (0, -1, True, 9007199254740992):
            with self.assertRaises(InvalidTopology):
                RingSnapshot(epoch, 128, ("a",))
        for nodes in (("a", "a"), ["a"], tuple(f"n{i}" for i in range(33))):
            with self.assertRaises(InvalidTopology):
                RingSnapshot(1, 128, nodes)
        for call in (lambda: self.ring.with_node(Node("redis_a"), 2), lambda: self.ring.without_node("missing", 2),
                     lambda: self.ring.with_node(Node("d"), 1), lambda: self.ring.without_node("redis_b", True),
                     lambda: self.ring.with_node("d", 2), lambda: HashRing(None)):
            with self.assertRaises(InvalidTopology):
                call()
        full = HashRing(RingSnapshot(1, 1, tuple(f"n{i}" for i in range(32))))
        with self.assertRaises(InvalidTopology):
            full.with_node(Node("extra"), 2)
        with self.assertRaises(TypeError):
            self.ring.locate("text")

    def test_empty_single(self):
        with self.assertRaises(NoNodes):
            HashRing(RingSnapshot(1))
        ring = HashRing(RingSnapshot(1, node_ids=("a",)))
        self.assertEqual({ring.locate(k) for k in self.keys}, {"a"})
        with self.assertRaises(NoNodes):
            ring.without_node("a", 2)
        self.assertEqual(ring.health(), {"state": "ok", "reason": None})

    def test_hot_key_access_is_not_balanced_by_vnodes(self):
        keys = [b"hot"] * 9900 + self.keys[:100]
        counts = {n: 0 for n in self.ring.snapshot().node_ids}
        for key in keys:
            counts[self.ring.locate(key)] += 1
        self.assertGreaterEqual(max(counts.values()), 9900)

    def test_concurrent_publication(self):
        # Lock protects coordinator publication/acquisition, then reads are lock-free.
        current = self.ring
        lock = threading.Lock()
        barrier = threading.Barrier(5)
        expected = {}
        for epoch in range(1, 31):
            nodes = ("redis_a", "redis_b", "redis_c") + (("redis_d",) if epoch % 2 == 0 else ())
            expected[epoch] = HashRing(RingSnapshot(epoch, 128, nodes))

        def reader():
            for epoch in range(2, 31):
                with lock:
                    captured = current
                self.assertEqual(captured.epoch, epoch - 1)
                barrier.wait()  # all readers captured old generation before update
                for i in range(100):
                    key = self.keys[i]
                    self.assertEqual(captured.locate(key), expected[captured.epoch].locate(key))
                    self.assertEqual(len(captured._positions), len(captured.snapshot().node_ids) * 128)
                barrier.wait()  # writer has published; retained generation is intact

        def writer():
            nonlocal current
            for epoch in range(2, 31):
                barrier.wait()
                with lock:
                    previous = current
                replacement = (previous.with_node(Node("redis_d"), epoch) if epoch % 2 == 0
                               else previous.without_node("redis_d", epoch))
                with lock:
                    current = replacement
                barrier.wait()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(reader) for _ in range(4)] + [pool.submit(writer)]
            for future in futures:
                future.result()
        self.assertEqual(current.epoch, 30)


if __name__ == "__main__":
    unittest.main()
