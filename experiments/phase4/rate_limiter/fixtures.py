"""Deterministic token-free synthetic decision workload."""
import random
from pulsegrid_rate_limiter import RoutePolicy

PARTITIONS = (
    RoutePolicy('doctor','directory_search','search'),
    RoutePolicy('patient','auth_login','login'),
    RoutePolicy('emergency','emergency_public','submission'),
    RoutePolicy('emergency','emergency_authenticated','submission'),
    RoutePolicy('emergency','emergency_staff','mutation'),
)

def workload(seed, count):
    rng=random.Random(seed)
    return [(0 if rng.random()<.5 else rng.randrange(1,100),rng.randrange(len(PARTITIONS)))
            for _ in range(count)]
