"""Validate actual polling coverage scheduling without inventing RX580 per-PID VRAM."""
import json
import unittest
from gputaskman.macos import FootprintPoller


def run_footprint(args, **kwargs):
    path = args[args.index('-j') + 1]
    pids = [int(args[i + 1]) for i, a in enumerate(args[:-1]) if a == '-p']
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'processes': [{'pid': pid, 'categories': {
            'IOAccelerator (graphics)': {'dirty': 2048 * pid},
            'IOSurface': {'dirty': 512 * pid}}} for pid in pids]}, f)


class FairGraphicsCoverage043(unittest.TestCase):
    def test_all_six_pids_get_measured_after_three_bounded_passes(self):
        m = FootprintPoller(run=run_footprint, clock=lambda: 100.0, batch_size=1, max_per_pass=2)
        m.set_targets([(pid, 'stable', True) for pid in range(1, 7)])
        for _ in range(3):
            m.poll_once()
        self.assertEqual(sum(m.get_graphics_map(pid, 'stable') is not None for pid in range(1, 7)), 6)
        self.assertEqual(m._scan_cursor, 0)

    def test_active_client_is_not_polled_every_view_refresh(self):
        calls = []
        tick = [100.0]
        def run(args, **kwargs):
            calls.append(1)
            run_footprint(args, **kwargs)
        m = FootprintPoller(run=run, clock=lambda: tick[0], batch_size=1, max_per_pass=1)
        m.set_targets([(10, 'stable', True)])
        m.poll_once(); m.poll_once()
        self.assertEqual(len(calls), 1)
        tick[0] = 119.0
        m.poll_once()
        self.assertEqual(len(calls), 2)

    def test_reused_pid_discards_negative_cache_and_backoff(self):
        m = FootprintPoller(run=run_footprint, clock=lambda: 100.0, batch_size=1)
        m.set_targets([(9, 'old', True)])
        m._retry[9] = 300.0
        m._fails[9] = 3
        m.set_targets([(9, 'new', True)])
        self.assertNotIn(9, m._retry)
        self.assertNotIn(9, m._fails)
        m.poll_once()
        self.assertEqual(m.get_graphics_map(9, 'new')['iosurface_bytes'], 512 * 9)

    def test_unknown_category_not_claimed_as_memory(self):
        def no_graphics(args, **kwargs):
            path = args[args.index('-j') + 1]
            pids = [int(args[i + 1]) for i, a in enumerate(args[:-1]) if a == '-p']
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'processes': [{'pid': pid, 'categories': {'MALLOC': {'dirty': 100}}} for pid in pids]}, f)
        m = FootprintPoller(run=no_graphics, clock=lambda: 100.0)
        m.set_targets([(3, 'stable', True)])
        m.poll_once()
        value = m.get_graphics_map(3, 'stable')
        self.assertEqual(value['graphics_map_status'], 'no_graphics_categories')
        self.assertIsNone(value['graphics_map_bytes'])

if __name__ == '__main__':
    unittest.main()
