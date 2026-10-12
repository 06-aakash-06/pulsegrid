import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[3] / "experiments/phase4/consistent_hashing/run.py"
spec = importlib.util.spec_from_file_location("ring_benchmark", path)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def test_synthetic_generator(self):
        first = benchmark.keys_for(404, 1000)
        self.assertEqual(first, benchmark.keys_for(404, 1000))
        self.assertNotEqual(first, benchmark.keys_for(405, 1000))
        self.assertEqual(len(set(first)), 1000)

    def test_nearest_rank(self):
        self.assertEqual(benchmark.percentile(list(range(100)), .95), 94)
        self.assertEqual(benchmark.percentile([7], .99), 7)

    def test_modulo_order(self):
        first = benchmark.Modulo(("c", "b", "a"))
        second = benchmark.Modulo(("a", "b", "c"))
        for key in benchmark.keys_for(404, 1000):
            self.assertEqual(first.locate(key), second.locate(key))


if __name__ == "__main__":
    unittest.main()
