"""Full collector footprint cache -> stream trend math; no GPU VRAM estimation."""
import json
import unittest
from gputaskman.macos import FootprintPoller
from gpu_memory_trends_045 import GraphicsTrends

class GPULivePipeline046(unittest.TestCase):
    def test_two_distinct_footprint_samples_and_repeated_ui_frame(self):
        t=[100.]
        values=[1048576, 3145728]
        commands=[]
        def run(args, **kw):
            commands.append(1)
            path=args[args.index('-j')+1]
            with open(path,'w') as f:
                json.dump({'processes':[{'pid':900,'categories':{'IOSurface':{'dirty':values[min(len(commands)-1,1)]}}}]},f)
        poller=FootprintPoller(run=run,clock=lambda:t[0],batch_size=1,max_per_pass=1)
        poller.set_targets([(900,'same-process',True)])
        trends=GraphicsTrends()
        poller.poll_once()
        first=poller.get_graphics_map(900,'same-process')
        row=dict(pid=900,started_at=10.,**first)
        trends.update([row],t[0]);self.assertEqual(row['graphics_trend_samples'],1)
        self.assertIsNone(row['graphics_change_bytes'])
        duplicate=dict(pid=900,started_at=10.,**first)
        trends.update([duplicate],t[0]+2)
        self.assertEqual(duplicate['graphics_trend_samples'],1)
        self.assertEqual(len(commands),1)
        t[0]=119.
        poller.poll_once()
        second=poller.get_graphics_map(900,'same-process')
        row2=dict(pid=900,started_at=10.,**second)
        trends.update([row2],t[0])
        self.assertEqual(len(commands),2)
        self.assertEqual(row2['graphics_trend_samples'],2)
        self.assertEqual(row2['graphics_change_bytes'],2097152)
        self.assertEqual(row2['graphics_peak_5m_bytes'],3145728)
    def test_no_false_change_from_valid_category_free_process(self):
        tr=GraphicsTrends()
        row=dict(pid=1,started_at=1.0,graphics_map_status='no_graphics_categories',
                 graphics_map_bytes=None,graphics_map_sample_clock=100.)
        tr.update([row],100.)
        self.assertIsNone(row['graphics_change_bytes'])
        self.assertIsNone(row['graphics_peak_5m_bytes'])
        self.assertEqual(row['graphics_trend_samples'],0)
    def test_pid_reuse_creates_fresh_baseline(self):
        tr=GraphicsTrends()
        a=dict(pid=1,started_at=1.,graphics_map_status='measured',graphics_map_bytes=1024,graphics_map_sample_clock=100.)
        tr.update([a],100.)
        b=dict(pid=1,started_at=2.,graphics_map_status='measured',graphics_map_bytes=2048,graphics_map_sample_clock=119.)
        tr.update([b],119.)
        self.assertIsNone(b['graphics_change_bytes'])
        self.assertEqual(b['graphics_trend_samples'],1)
if __name__=='__main__': unittest.main()
