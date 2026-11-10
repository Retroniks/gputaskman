import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'macos'))
from gpu_roster import ProcessRoster
class RosterTests(unittest.TestCase):
    def test_missing_living_pid_not_dropped(self):
        r=ProcessRoster(); live={12:1.,13:2.}
        r.update([{'pid':12,'gpu_pct':3.},{'pid':13}],live.get,now=1)
        rows=r.update([{'pid':13}],live.get,now=3)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['measurement_state'],'awaiting')
        self.assertIsNone(rows[0]['gpu_pct'])
    def test_dead_removed(self):
        r=ProcessRoster(); live={12:1.};r.update([{'pid':12}],live.get,now=1);live.clear()
        self.assertEqual(r.update([],live.get,now=2),[])
    def test_pid_reuse_removed(self):
        r=ProcessRoster();live={12:1.};r.update([{'pid':12}],live.get,now=1);live[12]=2.
        self.assertEqual(r.update([],live.get,now=2),[])
    def test_expired_removed(self):
        r=ProcessRoster(ttl=2); live={12:1.};r.update([{'pid':12}],live.get,now=1)
        self.assertEqual(r.update([],live.get,now=4),[])
    def test_returning_process_is_current(self):
        r=ProcessRoster(); live={12:1.};r.update([{'pid':12}],live.get,now=1)
        r.update([],live.get,now=2)
        self.assertEqual(r.update([{'pid':12,'gpu_pct':1.}],live.get,now=3)[0]['measurement_state'],'current')
