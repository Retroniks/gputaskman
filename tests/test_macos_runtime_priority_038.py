"""Original Intel Radeon Metal runtime and PID scan priority contracts."""
import unittest
from types import SimpleNamespace as Obj
from gputaskman.procinfo import macos_mapped_runtime, _match_runtimes
from gputaskman.macos_scan_priority import prioritize_radeon_processes


def row(pid, gpu, name='app', blocked=False):
    return Obj(pid=pid, name=name, gpu=Obj(gpu_pct=gpu),
               detail=Obj(access_denied=blocked))

class RuntimePriorityTests(unittest.TestCase):
    def test_radeon_mtl_bundle_mapped(self):
        path='/System/Library/Extensions/AMDRadeonX4000MTLDriver.bundle/Contents/MacOS/AMDRadeonX4000MTLDriver'
        evidence=macos_mapped_runtime(path)
        self.assertEqual(_match_runtimes({evidence}), ['Metal'])
    def test_apple_metal_framework_mapped(self):
        p='/System/Library/Frameworks/Metal.framework/Versions/A/Metal'
        self.assertEqual(_match_runtimes({macos_mapped_runtime(p)}), ['Metal'])
    def test_original_inspector_uses_mapped_metal_framework(self):
        from gputaskman import procinfo
        from unittest.mock import patch
        d=procinfo.ProcDetail(pid=123, name='render', exe='/usr/bin/test')
        mapped=Obj(path='/System/Library/Frameworks/Metal.framework/Versions/A/Metal', rss=0)
        with patch.object(procinfo, '_memory_maps', return_value=[mapped]),                 patch.object(procinfo.sys, 'platform', 'darwin'):
            procinfo.ProcInspector().scan(d)
        self.assertIn('Metal', d.runtimes)
    def test_no_gpu_runtime_fabricated_for_gl_or_random_file(self):
        for p in ('/System/Library/Extensions/AMDRadeonX4000GLDriver.bundle/Contents/MacOS/AMDRadeonX4000GLDriver',
                  '/tmp/metal-demo.txt', '/System/Library/Frameworks/Metal.framework/Resources/Info.plist'):
            self.assertIsNone(macos_mapped_runtime(p))
    def test_active_accessible_apps_before_other_user(self):
        rows=[row(1,0,blocked=True),row(2,0),row(3,4),row(4,9),row(5,0)]
        result=prioritize_radeon_processes(rows,{1:0,2:501,3:501,4:0,5:501},501,0)
        self.assertEqual(result[0].pid,3)
        self.assertEqual(result[-2].pid,1)
        self.assertEqual(result[-1].pid,4)
    def test_real_ai_clients_prioritized_without_creating_data(self):
        rows=[row(1,0),row(2,0,'llama-server'),row(3,0)]
        result=prioritize_radeon_processes(rows,{r.pid:501 for r in rows},501,0)
        self.assertEqual(result[0].pid,2)
        self.assertEqual({r.pid for r in rows},{r.pid for r in result})
    def test_idle_rotation_preserves_every_process(self):
        rows=[row(i,0) for i in range(1,23)]
        owners={r.pid:501 for r in rows}
        a=prioritize_radeon_processes(rows,owners,501,0)
        b=prioritize_radeon_processes(rows,owners,501,1)
        self.assertNotEqual(a[0].pid,b[0].pid)
        self.assertEqual({r.pid for r in a},{r.pid for r in b})

if __name__=='__main__': unittest.main()
