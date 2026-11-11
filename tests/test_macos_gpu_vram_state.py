import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'macos'))
from gpu_vram_state import LastVRAM
class VRAMTests(unittest.TestCase):
    def test_valid_reading(self):
        r=LastVRAM().apply({'vram_total':100,'vram_used':41},now=10)
        self.assertEqual((r['vram_used'],r['vram_value_state']),(41,'current'))
    def test_missing_keeps_last(self):
        v=LastVRAM();v.apply({'vram_total':100,'vram_used':41},now=10)
        r=v.apply({'vram_total':100,'vram_used':None},now=13)
        self.assertEqual((r['vram_used'],r['vram_value_state'],r['vram_value_age_s']),(41,'last',3))
    def test_never_observed_is_unknown(self):
        r=LastVRAM().apply({'vram_total':100,'vram_used':None},now=3)
        self.assertIsNone(r['vram_used']);self.assertEqual(r['vram_value_state'],'unavailable')
    def test_out_of_bounds_rejected(self):
        r=LastVRAM().apply({'vram_total':100,'vram_used':101},now=5)
        self.assertEqual(r['vram_value_state'],'unavailable')
    def test_zero_is_valid(self):
        r=LastVRAM().apply({'vram_total':100,'vram_used':0},now=5)
        self.assertEqual(r['vram_value_state'],'current')
if __name__=='__main__':unittest.main()
