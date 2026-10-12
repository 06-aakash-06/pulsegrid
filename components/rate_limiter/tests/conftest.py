import importlib.util
from pathlib import Path
import pytest

path = Path(__file__).resolve().parents[3]/'experiments/phase4/rate_limiter/resources.py'
spec = importlib.util.spec_from_file_location('owned_resources', path)
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)

@pytest.fixture
def redis_server():
    with resources.DisposableRedis() as server:
        yield server
