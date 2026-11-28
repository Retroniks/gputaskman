"""Preserve real 5-minute minimum and maximum across bounded native chart points."""
import unittest
from gpu_memory_trends_045 import GraphicsTrends, compact_extrema


def row(t, value, identity=1.0):
    return dict(pid=876, started_at=identity, graphics_map_status='measured',
                graphics_map_bytes=value, graphics_map_sample_clock=float(t))


class GraphicsHistoryExtrema048(unittest.TestCase):
    def test_old_64_tail_would_lose_a_real_early_peak(self):
        t=GraphicsTrends()
        for stamp in range(100, 220):
            # Extremes are real readings near the start, not in the last 64.
            value=(20_000_000 if stamp==115 else (0 if stamp==120 else 2_000_000))
            sample=row(stamp,value)
            t.update([sample],float(stamp))
        series=sample['graphics_series_5m']
        self.assertLessEqual(len(series),64)
        self.assertEqual(series[0],[100.0,2_000_000])
        self.assertEqual(series[-1],[219.0,2_000_000])
        self.assertIn([115.0,20_000_000],series)
        self.assertIn([120.0,0],series)
        self.assertEqual(sample['graphics_peak_5m_bytes'],20_000_000)
        self.assertEqual(sample['graphics_trend_samples'],120)
        self.assertEqual([x[0] for x in series],sorted({x[0] for x in series}))

    def test_no_invented_times_or_memory_values(self):
        source=[(float(i),i*i%125) for i in range(200)]
        selected=compact_extrema(source,64)
        self.assertLessEqual(len(selected),64)
        self.assertEqual(selected[0],list(source[0]))
        self.assertEqual(selected[-1],list(source[-1]))
        self.assertEqual(min(v for _,v in selected),min(v for _,v in source))
        self.assertEqual(max(v for _,v in selected),max(v for _,v in source))
        self.assertTrue(all(tuple(point) in source for point in selected))
        self.assertTrue(all(selected[i][0]<selected[i+1][0] for i in range(len(selected)-1)))

    def test_short_real_history_is_unmodified(self):
        source=[(100.0,0),(101.5,1024),(124.0,4096)]
        self.assertEqual(compact_extrema(source,64),[[100.0,0],[101.5,1024],[124.0,4096]])
        with self.assertRaises(ValueError): compact_extrema(source,3)

    def test_expired_peak_and_reused_pid_not_reused(self):
        trend=GraphicsTrends(window_s=300.)
        for stamp,value in [(100.,500000),(220.,1200),(401.,5000)]:
            sample=row(stamp,value)
            trend.update([sample],stamp)
        self.assertEqual(sample['graphics_peak_5m_bytes'],5000)
        self.assertEqual(sample['graphics_series_5m'],[[220.0,1200],[401.0,5000]])
        reused=row(430.,88,identity=2.)
        trend.update([reused],430.)
        self.assertEqual(reused['graphics_series_5m'],[[430.0,88]])
        self.assertIsNone(reused['graphics_change_bytes'])
        self.assertEqual(reused['graphics_trend_samples'],1)

if __name__=='__main__': unittest.main()
