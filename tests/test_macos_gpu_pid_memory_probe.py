import unittest
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location('gpu_pid_memory_probe', Path(__file__).resolve().parents[1] / 'macos/gpu_pid_memory_probe.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MemoryProofTests(unittest.TestCase):
    def test_graphics_and_iosurface_kept_separate(self):
        sample = {'processes': [{'pid': 13, 'categories': {
            'IOAccelerator (graphics)': {'dirty': 4096},
            'IOSurface': {'dirty': 2048},
            'Owned physical footprint (graphics)': {'dirty': 1024},
            'MALLOC': {'dirty': 70000}}}]}
        data = module.category_bytes(sample, 13)
        self.assertEqual(data['graphics_dirty'], 5120)
        self.assertEqual(data['iosurface_dirty'], 2048)
        self.assertEqual(data['ioaccelerator_dirty'], 4096)

    def test_no_pid_is_unknown(self):
        self.assertIsNone(module.category_bytes({'processes': []}, 1))

    def test_true_zero_is_not_unknown(self):
        sample = {'processes': [{'pid': 5, 'categories': {'IOAccelerator (graphics)': {'dirty': 0}}}]}
        self.assertEqual(module.category_bytes(sample, 5)['graphics_dirty'], 0)

    def test_invalid_categories_not_invented(self):
        sample = {'processes': [{'pid': 5, 'categories': []}]}
        self.assertIsNone(module.category_bytes(sample, 5))

    def test_non_numeric_values_ignored(self):
        sample = {'processes': [{'pid': 8, 'categories': {'IOAccelerator (graphics)': {'dirty': '42'}}}]}
        self.assertEqual(module.category_bytes(sample, 8)['graphics_dirty'], 0)


if __name__ == '__main__':
    unittest.main()
