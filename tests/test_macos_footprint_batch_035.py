"""No invented VRAM; batches must preserve per-process footprint and identity."""
import json
import unittest
from gputaskman.macos_footprint_batch import collect_graphics_batch
from gputaskman.macos import FootprintPoller, graphics_bytes

class BatchFootprintTests(unittest.TestCase):
    def source(self, counts, corrupt=False, missing=None):
        calls = []
        def run(args, **kw):
            pids = [int(args[i + 1]) for i, a in enumerate(args[:-1]) if a == '-p']
            calls.append(pids)
            if corrupt:
                return None
            rows = [{'pid':pid,'categories': {'IOAccelerator (graphics)': {'dirty':counts[pid]}}}
                    if counts[pid] is not None else {'pid':pid,'categories':{'MALLOC':{'dirty':77}}}
                    for pid in pids if pid != missing]
            with open(args[args.index('-j') + 1], 'w', encoding='utf-8') as out:
                json.dump({'processes': rows}, out)
        return run, calls
    def test_multiple_pid_values_and_real_zero(self):
        run, calls = self.source({1:0,2:4096,3:None})
        result = collect_graphics_batch([1,2,3], run, graphics_bytes)
        self.assertEqual(result,{1:(0,'measured'),2:(4096,'measured'),3:(None,'no_graphics_categories')})
        self.assertEqual(calls,[[1,2,3]])
    def test_missing_pid_rejects_full_batch(self):
        run, _ = self.source({1:20,2:30},missing=2)
        self.assertIsNone(collect_graphics_batch([1,2],run,graphics_bytes))
    def test_missing_json_never_means_zero(self):
        run, _ = self.source({1:20,2:30},corrupt=True)
        self.assertIsNone(collect_graphics_batch([1,2],run,graphics_bytes))
    def test_batch_with_parity_validation(self):
        run, calls = self.source({1:10,2:20,3:30})
        poller = FootprintPoller(run=run,clock=lambda:0.0,batch_size=3)
        poller.set_targets([(1,'a',True),(2,'a',True),(3,'a',True)])
        poller.poll_once()
        self.assertEqual([poller.get(i,'a') for i in (1,2,3)],[10,20,30])
        self.assertTrue(poller._batch_verified)
        self.assertEqual(calls,[[1,2,3],[1],[2],[3]])
    def test_group_disagreement_uses_single_process_values(self):
        def run(args, **kw):
            pids = [int(args[i + 1]) for i, a in enumerate(args[:-1]) if a == '-p']
            rows = [{'pid':pid,'categories':{'IOAccelerator':{'dirty':pid * (2 if len(pids)>1 else 1)}}}
                    for pid in pids]
            with open(args[args.index('-j')+1], 'w',encoding='utf-8') as out:
                json.dump({'processes':rows},out)
        poller = FootprintPoller(run=run,clock=lambda:0.0,batch_size=3)
        poller.set_targets([(1,'a',True),(2,'a',True),(3,'a',True)])
        poller.poll_once()
        self.assertTrue(poller._batch_disabled)
        self.assertEqual([poller.get(i,'a') for i in (1,2,3)],[1,2,3])
    def test_identity_reuse_discards_old_size(self):
        run, _ = self.source({1:2048,2:4096})
        poller = FootprintPoller(run=run,clock=lambda:0.0,batch_size=2)
        poller.set_targets([(1,'old',True),(2,'old',True)])
        poller.poll_once()
        poller.set_targets([(1,'new',True),(2,'old',True)])
        self.assertIsNone(poller.get(1,'new'))
        self.assertEqual(poller.get(2,'old'),4096)

if __name__=='__main__': unittest.main()
