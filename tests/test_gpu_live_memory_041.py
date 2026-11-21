"""Focused process category + PID reuse contracts for live memory display."""
import unittest
from gpu_live_memory_041 import LiveGraphicsMemory, split_graphics_categories


class LiveMemoryTests(unittest.TestCase):
    def test_independent_iosurface_and_ioaccelerator(self):
        value = split_graphics_categories({'categories': {
            'IOAccelerator (graphics)': {'dirty': 1200},
            'IOAccelerator': {'dirty': 200},
            'IOSurface': {'dirty': 400}}})
        self.assertEqual(value['graphics_map_bytes'], 1800)
        self.assertEqual(value['ioaccelerator_bytes'], 1400)
        self.assertEqual(value['iosurface_bytes'], 400)

    def test_unknown_not_zero(self):
        value = split_graphics_categories({'categories': {'IOAccelerator': {'dirty': 0}}})
        self.assertEqual(value['ioaccelerator_bytes'], 0)
        self.assertIsNone(value['iosurface_bytes'])
        self.assertEqual(value['graphics_map_bytes'], 0)

    def test_pid_reuse_discards_cache(self):
        m = LiveGraphicsMemory(start=False, clock=lambda: 30)
        m.set_targets([{'pid': 1, 'gpu_pct': 2}], [{'pid': 1, 'started_at': 10.0}])
        m._cache[(1, 10.0)] = (20, {'graphics_map_bytes': 100})
        self.assertEqual(m.read(1, 10.0)['graphics_map_bytes'], 100)
        m.set_targets([{'pid': 1, 'gpu_pct': 2}], [{'pid': 1, 'started_at': 11.0}])
        self.assertIsNone(m.read(1, 11.0))
        self.assertIsNone(m.read(1, 10.0))

    def test_expiration_and_non_gpu_process(self):
        m = LiveGraphicsMemory(start=False, clock=lambda: 100, ttl=20)
        m.set_targets([{'pid': 2, 'gpu_pct': 2}], [{'pid': 2, 'started_at': 10.0}, {'pid': 3, 'started_at': 10.0}])
        m._cache[(2, 10.0)] = (50, {'graphics_map_bytes': 70})
        self.assertIsNone(m.read(2, 10.0))
        self.assertNotIn((3, 10.0), m._targets)


if __name__ == '__main__':
    unittest.main()
