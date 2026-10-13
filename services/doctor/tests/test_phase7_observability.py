from doctor_service.phase4 import _record_hash_topology


def test_hash_topology_metrics_report_only_configured_epoch_and_node_count():
    observations = []

    class Observer:
        def gauge(self, name, value, labels):
            observations.append((name, value, labels))

    _record_hash_topology(Observer(), 17, 2)

    assert observations == [
        ("pulsegrid_consistent_hashing_topology_epoch", 17.0, {"owner": "doctor"}),
        ("pulsegrid_consistent_hashing_configured_nodes", 2.0, {"owner": "doctor"}),
    ]


def test_hash_topology_metrics_cannot_fail_cache_startup():
    class UnavailableObserver:
        def gauge(self, _name, _value, _labels):
            raise RuntimeError("metrics unavailable")

    _record_hash_topology(UnavailableObserver(), 17, 2)
