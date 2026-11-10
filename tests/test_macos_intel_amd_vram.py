"""Isolated fixture tests for Polaris VRAM counter accounting."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from gputaskman.macos_intel_amd_vram import vram_used_from_entries
T=8*1024**3
class TestVram(unittest.TestCase):
    def test_measured_used(self):
        self.assertEqual(vram_used_from_entries([{'PerformanceStatistics': {'vramFreeBytes': T-1024**3}}],T),1024**3)
    def test_nested_duplicate(self):
        data={'IORegistryEntryChildren':[{'PerformanceStatistics':{'vramFreeBytes':T-42}}, {'PerformanceStatistics':{'vramFreeBytes':T-42}}]}
        self.assertEqual(vram_used_from_entries([data],T),42)
    def test_unknown(self):
        self.assertIsNone(vram_used_from_entries([{'PerformanceStatistics':{'gartFreeBytes':42}}],T))
    def test_out_of_range(self):
        self.assertIsNone(vram_used_from_entries([{'PerformanceStatistics':{'vramFreeBytes':T+1}}],T))
    def test_conflicting(self):
        self.assertIsNone(vram_used_from_entries([{'PerformanceStatistics':{'vramFreeBytes':T-1}}, {'PerformanceStatistics':{'vramFreeBytes':T-2}}],T))
    def test_boolean_invalid(self):
        self.assertIsNone(vram_used_from_entries([{'PerformanceStatistics':{'vramFreeBytes':True}}],T))
if __name__=='__main__': unittest.main()
