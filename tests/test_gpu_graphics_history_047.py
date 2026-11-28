"""Per-process history points come from distinct real footprint sample timestamps only."""
import unittest
from gpu_memory_trends_045 import GraphicsTrends

def sample(t, value, pid=20, started=1.0, status='measured'):
    return {'pid':pid, 'started_at':started, 'graphics_map_status':status,
            'graphics_map_bytes':value, 'graphics_map_sample_clock':t}

class GraphicsMemoryHistory047(unittest.TestCase):
    def test_two_samples_repeat_frame_and_real_timestamp_spacing(self):
        tr=GraphicsTrends()
        for now, stamp, val in [(100,100,1024),(102,100,1024),(133,133,2048)]:
            row=sample(float(stamp),val)
            tr.update([row],float(now))
        self.assertEqual(row['graphics_series_5m'],[[100.0,1024],[133.0,2048]])
        self.assertEqual(row['graphics_trend_samples'],2)
        self.assertEqual(row['graphics_change_bytes'],1024)
    def test_stale_and_category_free_never_fabricate_history(self):
        tr=GraphicsTrends()
        row=sample(100.,3000)
        tr.update([row],100.)
        for state in ('stale','no_graphics_categories'):
            bad=sample(200.,None,status=state)
            tr.update([bad],200.)
            self.assertEqual(bad['graphics_series_5m'],[])
            self.assertEqual(bad['graphics_trend_samples'],0)
        good=sample(201.,2000)
        tr.update([good],201.)
        self.assertEqual(good['graphics_series_5m'],[[100.0,3000],[201.0,2000]])
    def test_five_minute_expiry_and_pid_reuse(self):
        tr=GraphicsTrends()
        for now, stamp, value in [(100,100,100),(250,250,200),(401,401,300)]:
            row=sample(float(stamp),value)
            tr.update([row],float(now))
        self.assertEqual(row['graphics_series_5m'],[[250.0,200],[401.0,300]])
        reused=sample(420.,555,started=2.0)
        tr.update([reused],420.)
        self.assertEqual(reused['graphics_series_5m'],[[420.0,555]])
        self.assertIsNone(reused['graphics_change_bytes'])
    def test_serialized_history_is_bounded_and_zero_is_valid(self):
        tr=GraphicsTrends()
        for stamp in range(100,172):
            row=sample(float(stamp),stamp-100)
            tr.update([row],float(stamp))
        self.assertEqual(row['graphics_trend_samples'],72)
        self.assertEqual(len(row['graphics_series_5m']),64)
        self.assertEqual(row['graphics_series_5m'][0],[108.0,8])
        self.assertEqual(row['graphics_series_5m'][-1],[171.0,71])
        self.assertEqual(row['graphics_peak_5m_bytes'],71)
        self.assertEqual(row['graphics_change_bytes'],1)
if __name__=='__main__': unittest.main()
