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
    matrix_summary,
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

    def test_three_consecutive_high_docker_cpu_samples_stop_safely(self):
        resources = [
            {
                "container": "docker-vm",
                "phase": "measurement",
                "sampled_utc": f"2026-10-13T10:00:0{second}+00:00",
                "cpu_percent": 360.0,
                "cpu_limit_percent": 400.0,
            }
            for second in range(3)
        ]
        result = guardrail_reason(
            [],
            resources,
            {},
            {},
        )
        self.assertIn("Docker VM CPU", result or "")

    def test_three_consecutive_high_host_load_samples_stop_safely(self):
        resources = [
            {
                "container": "mac-host",
                "phase": "measurement",
                "sampled_utc": f"2026-10-13T10:00:0{second}+00:00",
                "host_load_1m": 10.8,
                "host_cpu_count": 12,
            }
            for second in range(3)
        ]
        result = guardrail_reason([], resources, {}, {})
        self.assertIn("macOS one-minute load", result or "")

    def test_phase82_matrix_summary_marks_single_trial_as_limited_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "summaries").mkdir()
            for replicas in (1, 2):
                for concurrency, throughput in ((4, 100.0), (16, 80.0), (64, 50.0)):
                    summary = {
                        "replicas": replicas,
                        "concurrency": concurrency,
                        "successful_rps": throughput * replicas / 2,
                        "attempted_rps": throughput * replicas / 2,
                        "admitted_rps": throughput * replicas / 2,
                        "success_latency_ms": {"mean": 30.0 / replicas, "p95": 80.0 / replicas},
                        "rejection_percent": 0.0,
                        "http_5xx": 0,
                        "completed_http_responses": 1000,
                    }
                    (output / "summaries" / f"r{replicas}-c{concurrency}-t1.json").write_text(
                        json.dumps(summary)
                    )
            result = matrix_summary(output, trial_numbers=(1,))
            self.assertTrue(result["limited_statistical_evidence"])
            self.assertEqual(result["trial_count"], 1)
            self.assertAlmostEqual(
                result["scaling_comparison"]["low"]["throughput_improvement_ratio"], 2.0
            )
            self.assertAlmostEqual(
                result["scaling_comparison"]["low"]["scaling_efficiency_percent"], 100.0
            )

    def test_tracing_free_static_config_keeps_metrics_and_dynamic_routes(self):
        root = Path(__file__).resolve().parents[2]
        config = (root / "infra/traefik/traefik.phase8-benchmark.yaml").read_text()
        self.assertIn("metrics:", config)
        self.assertIn("entryPoint: metrics", config)
        self.assertIn("filename: /etc/traefik/routes.yaml", config)
        self.assertNotIn("\ntracing:", config)

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
