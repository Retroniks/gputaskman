"""Real footprint failures must be distinguishable from measured zero."""
import json
import unittest
from gputaskman.macos import FootprintPoller

class FootprintStatusTests(unittest.TestCase):
    def fake(self, categories=None, write=True, pid=420):
        def run(args, **kw):
            if write:
                with open(args[args.index('-j')+1],'w',encoding='utf-8') as f:
                    json.dump({'processes':[{'pid':pid,'categories':categories or {}}]},f)
        return run
    def poller(self,run):
        p=FootprintPoller(run=run,clock=lambda:0.0)
        p.set_targets([(420,'start',True)])
        return p
    def test_measured_graphics_bytes(self):
        p=self.poller(self.fake({'IOAccelerator (graphics)':{'dirty':9876}}))
        p.poll_once()
        self.assertEqual(p.get(420,'start'),9876)
        self.assertEqual(p.status(420,'start'),'measured')
    def test_real_zero_is_not_unknown(self):
        p=self.poller(self.fake({'IOSurface':{'dirty':0}}))
        p.poll_once()
        self.assertEqual(p.get(420,'start'),0)
        self.assertEqual(p.status(420,'start'),'measured')
    def test_no_graphics_category(self):
        p=self.poller(self.fake({'MALLOC':{'dirty':1000}}))
        p.poll_once()
        self.assertIsNone(p.get(420,'start'))
        self.assertEqual(p.status(420,'start'),'no_graphics_categories')
    def test_no_json_file(self):
        p=self.poller(self.fake(write=False))
        p.poll_once()
        self.assertEqual(p.status(420,'start'),'footprint_no_json')
    def test_pid_missing_in_json(self):
        p=self.poller(self.fake({'IOAccelerator':{'dirty':4}},pid=999))
        p.poll_once()
        self.assertEqual(p.status(420,'start'),'footprint_pid_missing')
    def test_process_identity_controls_results(self):
        p=self.poller(self.fake({'IOSurface':{'dirty':10}}))
        p.poll_once()
        p.set_targets([(420,'new',True)])
        self.assertEqual(p.status(420,'new'),'pending')
        self.assertIsNone(p.get(420,'new'))

if __name__=='__main__': unittest.main()
