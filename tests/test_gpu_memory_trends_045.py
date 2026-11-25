"""Actual reading identity and 5-minute graphics host-RAM peak contracts."""
import unittest
from gpu_memory_trends_045 import GraphicsTrends


class GraphicsTrends045(unittest.TestCase):
    def row(self, stamp, value, identity=1., state='measured', pid=20):
        return dict(pid=pid, started_at=identity, graphics_map_status=state,
                    graphics_map_bytes=value, graphics_map_sample_clock=stamp)

    def test_baseline_repeat_and_actual_change(self):
        t=GraphicsTrends()
        a=[self.row(100., 1024)]
        t.update(a, 100.); self.assertIsNone(a[0]['graphics_change_bytes'])
        self.assertEqual((a[0]['graphics_peak_5m_bytes'],a[0]['graphics_trend_samples']),(1024,1))
        b=[self.row(100., 1024)]
        t.update(b, 102.); self.assertEqual(b[0]['graphics_trend_samples'],1)
        self.assertIsNone(b[0]['graphics_change_bytes'])
        c=[self.row(111., 4096)]
        t.update(c, 112.); self.assertEqual((c[0]['graphics_change_bytes'],c[0]['graphics_peak_5m_bytes']),(3072,4096))
        d=[self.row(111., 4096)]
        t.update(d, 114.); self.assertEqual(d[0]['graphics_change_bytes'],3072)
        self.assertEqual(d[0]['graphics_trend_samples'],2)

    def test_negative_delta_and_measured_zero(self):
        t=GraphicsTrends()
        for stamp,value in [(100.,4000),(110.,0)]:
            a=[self.row(stamp,value)]; t.update(a,stamp)
        self.assertEqual(a[0]['graphics_change_bytes'],-4000)
        self.assertEqual(a[0]['graphics_peak_5m_bytes'],4000)

    def test_identity_reuse_and_exit_resets_history(self):
        t=GraphicsTrends(); a=[self.row(100.,500)]
        t.update(a,100.)
        b=[self.row(120.,100,identity=2.)]
        t.update(b,120.); self.assertIsNone(b[0]['graphics_change_bytes'])
        self.assertEqual(b[0]['graphics_peak_5m_bytes'],100)
        t.update([],121.); self.assertEqual(t._history,{})

    def test_valid_nographics_and_stale_never_fake_zero(self):
        t=GraphicsTrends(); a=[self.row(100.,500)]
        t.update(a,100.)
        b=[self.row(110.,None,state='no_graphics_categories')]
        t.update(b,110.); self.assertIsNone(b[0]['graphics_change_bytes'])
        self.assertIsNone(b[0]['graphics_peak_5m_bytes'])
        c=[self.row(111.,200,state='stale')]
        t.update(c,111.); self.assertIsNone(c[0]['graphics_change_bytes'])
        d=[self.row(112.,100)]
        t.update(d,112.); self.assertEqual(d[0]['graphics_change_bytes'],-400)

    def test_window_prunes_peak_without_extra_sample(self):
        t=GraphicsTrends(window_s=300.)
        for stamp,val in [(100.,1000),(250.,500),(390.,250)]:
            a=[self.row(stamp,val)]; t.update(a,stamp)
        self.assertEqual(a[0]['graphics_peak_5m_bytes'],1000)
        # At t=401, earliest t=100 lies outside [101,401].
        a=[self.row(390.,250)]; t.update(a,401.)
        self.assertEqual(a[0]['graphics_peak_5m_bytes'],500)
        self.assertEqual(a[0]['graphics_trend_samples'],2)

    def test_invalid_and_future_sample_rejected(self):
        t=GraphicsTrends()
        for sample in [self.row(200.,200),self.row(100.,True),self.row(99.,-1)]:
            t.update([sample],100.)
            self.assertIsNone(sample['graphics_peak_5m_bytes'])

if __name__=='__main__':unittest.main()
