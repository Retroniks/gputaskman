"""Provenance and missing-value contracts for Intel AMD per-PID graphics RAM."""
import unittest
from gputaskman.macos import graphics_bytes

class GraphicsCategoryTests(unittest.TestCase):
    def test_explicit_categories_dont_double_count_standalone(self):
        row = {'categories': {
            'IOAccelerator (graphics)': {'dirty': 1200},
            'Owned physical footprint (unmapped) (graphics)': {'dirty': 3400},
            'IOAccelerator': {'dirty': 1200},
            'IOSurface': {'dirty': 600},
            'MALLOC': {'dirty': 30_000}}}
        self.assertEqual(graphics_bytes(row), 5200)

    def test_intel_standalone_categories(self):
        row={'categories': {'VM: IOAccelerator': {'dirty': 4000},
                            'VM: IOSurface': {'dirty': 500},
                            'MALLOC': {'dirty': 9000}}}
        self.assertEqual(graphics_bytes(row), 4500)

    def test_measured_zero_is_zero(self):
        self.assertEqual(graphics_bytes({'categories': {'IOAccelerator': {'dirty': 0}}}), 0)

    def test_no_graphics_categories_means_unavailable(self):
        self.assertIsNone(graphics_bytes({'categories': {'MALLOC': {'dirty': 80000}}}))
        self.assertIsNone(graphics_bytes({'categories': {}}))
        self.assertIsNone(graphics_bytes({}))

    def test_invalid_dirty_values_are_unknown(self):
        self.assertIsNone(graphics_bytes({'categories': {'IOSurface': {'dirty': -1}}}))
        self.assertIsNone(graphics_bytes({'categories': {'IOAccelerator': {'dirty': True}}}))
        self.assertIsNone(graphics_bytes({'categories': {'IOAccelerator': {'dirty': '42'}}}))

if __name__=='__main__':
    unittest.main()
