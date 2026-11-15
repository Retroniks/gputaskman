import unittest
from gpu_metal_vram_analysis_036 import comparison, median_valid


class MetalCalibrationTests(unittest.TestCase):
    def test_median_removes_missing_and_preserves_measured_zero(self):
        self.assertEqual(median_valid([None, 0, 4, 8]),4)
        self.assertIsNone(median_valid([None, float('nan'), -1, True]))
    def test_comparison_does_not_invent_per_pid_vram(self):
        result=comparison([100, 100, 100],[132,132,132],[196,196,196],[100,100,100])
        self.assertEqual(result['device_vram_deltas_from_baseline_bytes']['metal_96_mib'],96)
        self.assertTrue(result['staged_device_counter_increase_observed'])
        self.assertIn('NOT per-process VRAM ownership',result['attribution'])
    def test_missing_value_remains_unknown(self):
        result=comparison([10,10,10],[None,None],[None],[5,5,5])
        self.assertIsNone(result['device_vram_deltas_from_baseline_bytes']['metal_32_mib'])
        self.assertFalse(result['staged_device_counter_increase_observed'])
    def test_decreasing_device_vram_is_not_clamped_to_zero(self):
        result=comparison([500,500,500],[450,450],[400,400],[350,350])
        self.assertEqual(result['device_vram_deltas_from_baseline_bytes']['metal_96_mib'],-100)
        self.assertFalse(result['staged_device_counter_increase_observed'])

if __name__ == '__main__': unittest.main()
