"""Only real device VRAM readings are published; no per-process VRAM invention."""
import unittest
from gputaskman.macos_intel_amd_vram import vram_measurement, vram_used_from_entries

class RadeonVRAM039(unittest.TestCase):
    def test_direct_counter_preferred(self):
        p=[{'PerformanceStatistics':{'vramUsedBytes':256,'vramFreeBytes':900}}]
        self.assertEqual(vram_measurement(p,1024),(256,'vramUsedBytes'))
    def test_free_counter_fallback(self):
        p=[{'PerformanceStatistics':{'vramFreeBytes':100}}]
        self.assertEqual(vram_measurement(p,1024),(924,'total_minus_vramFreeBytes'))
    def test_nested_duplicate_is_not_ambiguous(self):
        p={'children':[{'PerformanceStatistics':{'vramUsedBytes':500}}]*2}
        self.assertEqual(vram_used_from_entries(p,1024),500)
    def test_conflicting_direct_is_unknown(self):
        p=[{'PerformanceStatistics':{'vramUsedBytes':200}},
           {'PerformanceStatistics':{'vramUsedBytes':300,'vramFreeBytes':400}}]
        self.assertEqual(vram_measurement(p,1024),(None,'ambiguous_vramUsedBytes'))
    def test_out_of_range_and_bool_not_used(self):
        p=[{'PerformanceStatistics':{'vramUsedBytes':True,'vramFreeBytes':1500}}]
        self.assertIsNone(vram_used_from_entries(p,1024))
    def test_measured_zero_stays_zero(self):
        p=[{'PerformanceStatistics':{'vramUsedBytes':0}}]
        self.assertEqual(vram_used_from_entries(p,1024),0)
    def test_missing_source_is_unknown(self):
        self.assertEqual(vram_measurement([],1024),(None,'driver_counter_unavailable'))
    def test_invalid_total_unknown(self):
        self.assertIsNone(vram_used_from_entries([{'PerformanceStatistics':{'vramUsedBytes':50}}],0))
