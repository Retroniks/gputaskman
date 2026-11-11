import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'macos'))
from gpu_active import active_summary
class ActivityTests(unittest.TestCase):
    def test_current_positive(self):
        d=active_summary([{'pid':1,'name':'GPU','gpu_value_state':'current','gpu_pct':2.5}])
        self.assertEqual(d['gpu_active_count'],1)
        self.assertEqual(d['gpu_top_process']['pid'],1)
    def test_stale_value_not_active(self):
        self.assertEqual(active_summary([{'pid':1,'gpu_value_state':'last','gpu_pct':20}])['gpu_active_count'],0)
    def test_zero_not_active(self):
        self.assertEqual(active_summary([{'pid':1,'gpu_value_state':'current','gpu_pct':0}])['gpu_active_count'],0)
    def test_missing_not_active(self):
        self.assertEqual(active_summary([{'pid':1,'gpu_value_state':'current','gpu_pct':None}])['gpu_active_count'],0)
    def test_top_sorted_by_gpu(self):
        d=active_summary([{'pid':1,'name':'A','gpu_value_state':'current','gpu_pct':3},
                          {'pid':2,'name':'B','gpu_value_state':'current','gpu_pct':9}])
        self.assertEqual(d['gpu_top_process']['pid'],2)
        self.assertEqual(d['gpu_active_count'],2)
if __name__=='__main__': unittest.main()
