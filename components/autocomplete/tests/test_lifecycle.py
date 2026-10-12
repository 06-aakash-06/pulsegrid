from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from pulsegrid_autocomplete import (
    IndexLimits,
    IndexRegistry,
    IndexTooLarge,
    Suggestion,
    build_snapshot,
    refresh_index,
)


def item(resource_id: int, label: str) -> Suggestion:
    return Suggestion(str(resource_id), "doctor", label)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_limits_and_exact_generation(self) -> None:
        snapshot = build_snapshot(3, [item(1, "Ada Chen"), item(2, "Ada Li")])
        self.assertEqual(3, snapshot.generation)
        self.assertEqual(2, snapshot.entries)
        deduplicated = build_snapshot(4, [item(1, "Ada Chen"), item(1, "Ada Chen")])
        self.assertEqual(1, deduplicated.entries)
        with self.assertRaises(IndexTooLarge) as entry_limit:
            build_snapshot(4, [item(1, "Ada Chen"), item(2, "Ada Li")], IndexLimits(1, 1024))
        self.assertGreater(entry_limit.exception.estimated_bytes, 0)
        with self.assertRaises(IndexTooLarge) as context:
            build_snapshot(5, [item(1, "Ada Chen")], IndexLimits(10, 1024))
        self.assertEqual("memory_limit_exceeded", context.exception.reason)
        with self.assertRaises(ValueError):
            build_snapshot(6, [item(1, "Ada Chen"), item(1, "Ada Li")])

    async def test_refresh_retries_revision_race_and_publishes_once(self) -> None:
        class Ports:
            owner = "doctor"
            index_registry = IndexRegistry()
            index_limits = IndexLimits(100, 1024 * 1024)

            def __init__(self) -> None:
                self.reads = iter((1, 2, 2, 2, 2))
                self.loaded = 0

            @asynccontextmanager
            async def read_session(self):
                yield object()

            async def read_revision(self, session):
                return next(self.reads)

            async def load_snapshot(self, session):
                self.loaded += 1
                revision = 1 if self.loaded == 1 else 2
                return revision, (item(revision, f"Ada {revision}"),)

        ports = Ports()
        await refresh_index(ports)
        result = ports.index_registry.snapshot
        self.assertIsNotNone(result)
        self.assertEqual(2, result.generation)
        self.assertIs(result, ports.index_registry.snapshot)
        self.assertEqual("ok", (await ports.index_registry.health())["state"])

    async def test_refresh_limit_failure_degrades_without_publishing_partial_index(self) -> None:
        class Ports:
            owner = "doctor"
            index_registry = IndexRegistry()
            index_limits = IndexLimits(1, 1024 * 1024)

            @asynccontextmanager
            async def read_session(self):
                yield object()

            async def read_revision(self, session):
                return 9

            async def load_snapshot(self, session):
                return 9, (item(1, "Ada Chen"), item(2, "Ada Li"))

        ports = Ports()
        self.assertIsNone(await refresh_index(ports))
        self.assertIsNone(ports.index_registry.snapshot)
        self.assertEqual("degraded", (await ports.index_registry.health())["state"])

    async def test_concurrent_readers_see_whole_old_or_new_snapshot(self) -> None:
        registry = IndexRegistry()
        old = build_snapshot(1, [item(1, "Aster Old"), item(2, "Aster Older")])
        registry.publish(old)

        class Ports:
            owner = "doctor"
            index_registry = registry
            index_limits = IndexLimits(100, 1024 * 1024)

            @asynccontextmanager
            async def read_session(self):
                yield object()

            async def read_revision(self, session):
                return 2

            async def load_snapshot(self, session):
                return 2, (item(3, "Aster New"), item(4, "Aster Newer"))

        ports = Ports()

        def reader() -> set[tuple[int, ...]]:
            observed: set[tuple[int, ...]] = set()
            for _ in range(200):
                snapshot = registry.snapshot
                if snapshot is not None:
                    observed.add(
                        tuple(
                            int(value.id)
                            for value in snapshot.trie.search("aster", 20, ("doctor",))
                        )
                    )
            return observed

        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=8) as executor:
            read_tasks = [loop.run_in_executor(executor, reader) for _ in range(32)]
            refresh_task = asyncio.create_task(refresh_index(ports))
            observed_groups = await asyncio.gather(*read_tasks)
            await refresh_task
        observed = {value for group in observed_groups for value in group}
        self.assertTrue(observed)
        self.assertTrue(observed.issubset({(1, 2), (3, 4)}))
        self.assertEqual(2, registry.snapshot.generation)
        self.assertEqual((3, 4), tuple(int(value.id) for value in registry.snapshot.trie.search("aster", 20, ("doctor",))))

    async def test_out_of_order_publication_is_rejected(self) -> None:
        registry = IndexRegistry()
        registry.publish(build_snapshot(5, [item(1, "Ada")]))
        with self.assertRaises(ValueError):
            registry.publish(build_snapshot(4, [item(2, "Ada")]))


if __name__ == "__main__":
    unittest.main()

class PollCostTests(unittest.IsolatedAsyncioTestCase):
    async def _poll(self, changed=False, oversized=False):
        from pulsegrid_autocomplete.lifecycle import refresh_loop
        stop=asyncio.Event()
        class Ports:
            owner='doctor'
            def __init__(self):
                self.index_registry=IndexRegistry();self.loads=0;self.reads=0
                self.index_limits=IndexLimits(100,1024 if oversized else 1024*1024)
                if not oversized:self.index_registry.publish(build_snapshot(1,[item(1,'Ada Chen')]))
            @asynccontextmanager
            async def read_session(self):yield object()
            async def read_revision(self,session):
                self.reads+=1
                if self.reads>= (5 if oversized else 3):stop.set()
                return 2 if changed and self.reads>=2 else 1
            async def load_snapshot(self,session):
                self.loads+=1
                return (2 if changed else 1),(item(1,'Ada Chen'),)
        ports=Ports()
        await asyncio.wait_for(refresh_loop(ports,stop,interval_seconds=.001),1)
        return ports
    async def test_unchanged_revision_does_not_rebuild(self):
        ports=await self._poll();self.assertEqual(0,ports.loads);self.assertEqual(1,ports.index_registry.snapshot.generation)
    async def test_revision_change_rebuilds_and_publishes(self):
        ports=await self._poll(changed=True);self.assertEqual(1,ports.loads);self.assertEqual(2,ports.index_registry.snapshot.generation)
    async def test_unchanged_oversize_catalog_does_not_repeatedly_build(self):
        ports=await self._poll(oversized=True);self.assertEqual(1,ports.loads);self.assertEqual('memory_limit_exceeded',ports.index_registry.view.reason)
