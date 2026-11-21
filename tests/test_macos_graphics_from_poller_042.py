"""Single collection source for native per-PID IOSurface and IOAccelerator fields."""
import json
import unittest
from gputaskman.macos import FootprintPoller
from gputaskman.macos_graphics_breakdown import split_graphics_categories


def fake_run(args, **kwargs):
    path = args[args.index('-j')+1]
    ids = [int(args[i+1]) for i,v in enumerate(args[:-1]) if v == '-p']
    with open(path, 'w') as f:
        json.dump({'processes':[{'pid':pid, 'categories':{
            'IOAccelerator (graphics)':{'dirty':pid*100},
            'IOAccelerator':{'dirty':pid*10},
            'IOSurface':{'dirty':pid*20},
            'CoreAnimation':{'dirty':400}}} for pid in ids]}, f)

class MemoryFromPoller(unittest.TestCase):
    def test_categories_ignore_unrelated_rendering(self):
        d=split_graphics_categories({'categories':{
            'IOAccelerator (graphics)':{'dirty':100},'IOAccelerator':{'dirty':10},
            'IOSurface':{'dirty':25},'CoreAnimation':{'dirty':400}}})
        self.assertEqual(d['graphics_map_bytes'],135)
        self.assertEqual(d['ioaccelerator_bytes'],110)
        self.assertEqual(d['iosurface_bytes'],25)
    def test_zero_and_unknown(self):
        self.assertEqual(split_graphics_categories({'categories':{'IOSurface':{'dirty':0}}})['graphics_map_bytes'],0)
        self.assertIsNone(split_graphics_categories({'categories':{'MALLOC':{'dirty':100}}})['graphics_map_bytes'])
        self.assertIsNone(split_graphics_categories({'categories':{'IOSurface':{'dirty':-2}}})['graphics_map_bytes'])
    def test_single_source_caches_memory_map(self):
        m=FootprintPoller(run=fake_run,clock=lambda:20.0,batch_size=1)
        m.set_targets([(1,'a',True)])
        m.poll_once()
        data=m.get_graphics_map(1,'a')
        self.assertEqual(data['graphics_map_bytes'],130)
        self.assertEqual(data['ioaccelerator_bytes'],110)
        self.assertEqual(data['iosurface_bytes'],20)
        self.assertEqual(data['graphics_map_status'],'measured')
        self.assertIsNone(m.get_graphics_map(1,'b'))
    def test_batch_one_command_for_two_process_maps(self):
        calls=[]
        def run(args,**kw):
            calls.append(args)
            return fake_run(args,**kw)
        m=FootprintPoller(run=run,clock=lambda:30.0,batch_size=2)
        m.set_targets([(1,'a',True),(2,'a',True)])
        m.poll_once()
        self.assertEqual(m.get_graphics_map(1,'a')['graphics_map_bytes'],130)
        self.assertEqual(m.get_graphics_map(2,'a')['graphics_map_bytes'],260)
        self.assertTrue(m._batch_verified)
    def test_identity_reuse_discards_map(self):
        m=FootprintPoller(run=fake_run,clock=lambda:50.0,batch_size=1)
        m.set_targets([(1,'before',True)])
        m.poll_once()
        m.set_targets([(1,'after',True)])
        self.assertIsNone(m.get_graphics_map(1,'before'))
        self.assertIsNone(m.get_graphics_map(1,'after'))

if __name__=='__main__': unittest.main()
