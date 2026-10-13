from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_matrix import (
    DoctorRoute,
    DockerStatsSampler,
    benchmark_route_upstream_counts,
    guardrail_reason,
    load_progress,
    mark_case_started,
    profile_replica_deltas,
)


class MatrixHelpersTests(unittest.TestCase):
    def test_active_phase4_traefik_route_supports_one_and_two_benchmark_upstreams(self):
        source = Path(__file__).resolve().parents[2] / "infra/phase4/routes.yaml"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.yaml"
            path.write_bytes(source.read_bytes())
            route = DoctorRoute(path)
            try:
                route.activate()
                self.assertEqual(route.set_replicas(1), "phase8-one.localhost")
                self.assertEqual(benchmark_route_upstream_counts(path.read_bytes(), 1), (1, 0))
                self.assertEqual(route.set_replicas(2), "phase8-two.localhost")
                self.assertEqual(benchmark_route_upstream_counts(path.read_bytes(), 2), (1, 1))
            finally:
                route.restore()

    def test_doctor_route_adds_isolated_one_and_two_upstream_hosts_then_restores(self):
        original = (
            b"http:\n  routers:\n    doctor:\n      rule: Path(`/api/v1/doctors`)\n"
            b"      service: doctor\n    appointment:\n      rule: Path(`/api/v1/appointments`)\n"
            b"      service: appointment\n  services:\n    doctor:\n      loadBalancer:\n"
            b"        servers:\n          - url: http://doctor:8000\n"
            b"    appointment:\n      loadBalancer:\n        servers:\n"
            b"          - url: http://appointment:8000\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.yaml"
            path.write_bytes(original)
            route = DoctorRoute(path)
            route.activate()
            self.assertIn(b"Host(`phase8-one.localhost`)", path.read_bytes())
            self.assertIn(b"Host(`phase8-two.localhost`)", path.read_bytes())
            self.assertEqual(route.set_replicas(1), "phase8-one.localhost")
            self.assertEqual(benchmark_route_upstream_counts(path.read_bytes(), 1), (1, 0))
            self.assertIn(b"http://doctor_replica:8000", path.read_bytes())
            self.assertEqual(route.set_replicas(2), "phase8-two.localhost")
            self.assertEqual(benchmark_route_upstream_counts(path.read_bytes(), 2), (1, 1))
            restored_hash = route.restore()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(restored_hash, route.original_hash)
            self.assertFalse(route.backup.exists())

    def test_memory_unit_parser(self):
        self.assertEqual(DockerStatsSampler._bytes("82.50MiB"), int(82.5 * 1024**2))
        self.assertEqual(DockerStatsSampler._bytes("1.5GB"), int(1.5 * 1000**3))
        self.assertIsNone(DockerStatsSampler._bytes("unknown"))

    def test_profile_replica_counter_delta(self):
        route = "/api/v1/doctors/{doctor_id}"

        def snapshot(values):
            return {
                "queries": {
                    "doctor_http": {
                        "data": {
                            "result": [
                                {
                                    "metric": {
                                        "route": route,
                                        "status_class": "2xx",
                                        "replica_source": source,
                                    },
                                    "value": [1, str(value)],
                                }
                                for source, value in values.items()
                            ]
                        }
                    }
                }
            }

        result = profile_replica_deltas(
            snapshot({"doctor": 10, "doctor_replica": 20}),
            snapshot({"doctor": 35, "doctor_replica": 28}),
        )
        self.assertEqual(result, {"doctor": 25, "doctor_replica": 8})

    def test_restart_memory_and_five_second_5xx_guardrails(self):
        before = {
            "api": {"status": "running", "health": "healthy", "restart_count": 1}
        }
        after = {
            "api": {"status": "running", "health": "healthy", "restart_count": 1}
        }
        memory_stop = guardrail_reason(
            [],
            [{"container": "api", "memory_percent": 90.0}],
            before,
            after,
        )
        self.assertIn("memory limit", memory_stop or "")
        restart_stop = guardrail_reason(
            [],
            [],
            before,
            {"api": {"status": "running", "health": "healthy", "restart_count": 2}},
        )
        self.assertIn("restart", restart_stop or "")
        errors = [
            {
                "started_monotonic_s": second + index / 100,
                "classification": "server_error",
            }
            for second in range(10, 15)
            for index in range(10)
        ]
        server_error_stop = guardrail_reason(errors, [], before, after)
        self.assertIn("5xx", server_error_stop or "")

    def test_progress_prevents_repeating_started_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            progress = load_progress(path, "run", "commit")
            mark_case_started(progress, path, "l1-c4-t1")
            restored = json.loads(path.read_text())
            self.assertEqual(restored["started_cases"], ["l1-c4-t1"])
            self.assertNotIn("l1-c4-t1", restored["completed_cases"])

    def test_guardrail_stopped_matrix_cannot_be_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text(
                json.dumps(
                    {
                        "run_id": "run",
                        "starting_commit": "commit",
                        "started_cases": ["l1-c4-t1"],
                        "completed_cases": ["l1-c4-t1"],
                        "guardrail_stops": [
                            {"case_id": "l1-c4-t1", "reason": "memory threshold"}
                        ],
                    }
                )
            )
            with self.assertRaisesRegex(RuntimeError, "stopped on a guardrail"):
                load_progress(path, "run", "commit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
