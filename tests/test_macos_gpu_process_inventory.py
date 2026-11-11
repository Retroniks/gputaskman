import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / 'macos' / 'gpu_process_inventory.py'
spec = importlib.util.spec_from_file_location('inventory', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def proc(pid, born, cpu=2.0):
    return {'pid': pid, 'started_at': born, 'name': f'app{pid}', 'cpu_pct': cpu}


class InventoryTests(unittest.TestCase):
    def test_live_process_survives_missing_gpu(self):
        inv = module.ProcessInventory()
        inv.update([proc(15, 10)], [{'pid': 15, 'gpu_pct': 4, 'vram_bytes': 123}], now=1)
        r = inv.update([proc(15, 10)], [], now=10000)[0]
        self.assertEqual(r['gpu_pct'], 4)
        self.assertEqual(r['vram_bytes'], 123)
        self.assertEqual(r['gpu_value_state'], 'last')
        self.assertEqual(r['cpu_pct'], 2)
    def test_never_seen_gpu_keeps_process_visible(self):
        row = module.ProcessInventory().update([proc(9, 1)], [], now=5)[0]
        self.assertEqual(row['gpu_value_state'], 'unavailable')
        self.assertIsNone(row['gpu_pct'])
    def test_pid_reuse_does_not_inherit_other_process_memory(self):
        inv = module.ProcessInventory()
        inv.update([proc(9, 1)], [{'pid':9, 'vram_bytes':444}], now=1)
        row = inv.update([proc(9, 2)], [], now=2)[0]
        self.assertIsNone(row['vram_bytes'])
    def test_dead_process_removed(self):
        inv = module.ProcessInventory()
        inv.update([proc(9, 1)], [{'pid':9, 'vram_bytes':444}], now=1)
        self.assertEqual(inv.update([], [], now=2), [])
    def test_zero_is_real_measurement(self):
        row = module.ProcessInventory().update([proc(8, 1)], [{'pid':8, 'gpu_pct':0.0}], now=2)[0]
        self.assertEqual(row['gpu_value_state'], 'current')
        self.assertEqual(row['gpu_pct'], 0.0)
    def test_last_value_timestamp(self):
        inv = module.ProcessInventory()
        inv.update([proc(8, 1)], [{'pid':8, 'gpu_pct':4.0}], now=2)
        row=inv.update([proc(8, 1)], [], now=5)[0]
        self.assertEqual(row['gpu_value_age_s'], 3.0)

if __name__ == '__main__': unittest.main()
