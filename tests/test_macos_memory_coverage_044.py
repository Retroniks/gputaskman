"""Diagnostic coverage semantics; never translate host memory to dedicated Radeon VRAM."""
import json
import unittest
from gputaskman.macos import FootprintPoller


def example_run(args, **kw):
    path = args[args.index('-j') + 1]
    ids = [int(args[i + 1]) for i, v in enumerate(args[:-1]) if v == '-p']
    rows = []
    for pid in ids:
        if pid == 3:  # simulate footprint subprocess without JSON
            continue
        rows.append({'pid': pid, 'categories': (
            {'IOSurface': {'dirty': 1024}} if pid == 1 else {'MALLOC_SMALL': {'dirty': 200}})})
    if 3 not in ids:
        with open(path, 'w') as f:
            json.dump({'processes': rows}, f)

class Coverage044(unittest.TestCase):
    def test_measured_no_category_and_command_error_distinct(self):
        m = FootprintPoller(run=example_run, clock=lambda:100.0, batch_size=1)
        m.set_targets([(i, 'same', True) for i in (1,2,3)])
        m.poll_once()
        c=m.coverage_snapshot()
        self.assertEqual((c['total'], c['measured'], c['no_graphics_categories'], c['errors'], c['pending']), (3,1,1,1,0))
        self.assertEqual(c['attempted'],3)
        self.assertEqual(m.get_graphics_map(2,'same')['graphics_map_status'],'no_graphics_categories')
        self.assertEqual(m.get_graphics_map(3,'same')['graphics_map_status'],'footprint_no_json')
        self.assertIsNone(m.get_graphics_map(2,'same').get('graphics_map_bytes'))
    def test_negative_category_does_not_trigger_failure_backoff(self):
        m=FootprintPoller(run=example_run, clock=lambda:100.0, batch_size=1)
        m.set_targets([(2,'same',True)])
        for _ in range(4):m.poll_once()
        self.assertEqual(m._fails.get(2),None)
        self.assertEqual(m._retry.get(2),None)
        self.assertEqual(m.coverage_snapshot()['no_graphics_categories'],1)
    def test_no_category_refreshes_after_interval_and_becomes_measured(self):
        time_now=[100.0]
        calls=[]
        def dynamic(args, **kw):
            calls.append(1)
            path=args[args.index('-j')+1]
            category=({'MALLOC_SMALL':{'dirty':400}} if len(calls)==1 else {'IOSurface':{'dirty':600}})
            with open(path,'w') as f:json.dump({'processes':[{'pid':2,'categories':category}]},f)
        m=FootprintPoller(run=dynamic,clock=lambda:time_now[0],batch_size=1)
        m.set_targets([(2,'same',True)])
        m.poll_once()
        time_now[0]=130.0
        m.poll_once()
        self.assertEqual(len(calls),1)
        time_now[0]=161.0
        m.poll_once()
        self.assertEqual(m.coverage_snapshot()['measured'],1)
        self.assertEqual(len(calls),2)
    def test_pending_stale_and_reused_pid(self):
        now=[20.0]
        m=FootprintPoller(run=example_run,clock=lambda:now[0],batch_size=1)
        m.set_targets([(1,'one',True),(2,'two',True)])
        self.assertEqual(m.coverage_snapshot()['pending'],2)
        m.poll_once()
        now[0]=200.0
        self.assertEqual(m.coverage_snapshot()['stale'],2)
        self.assertEqual(m.get_graphics_map(1,'one')['graphics_map_status'],'stale')
        m.set_targets([(1,'changed',True),(2,'two',True)])
        self.assertIsNone(m.get_graphics_map(1,'changed'))
        self.assertIsNone(m.get_graphics_map(1,'one'))

if __name__=='__main__':unittest.main()
