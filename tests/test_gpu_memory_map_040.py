"""Source-based contracts for macOS GPU memory map: no Radeon VRAM inventions."""
import unittest
from gpu_memory_map_040 import category_rows, summarize, valid_int, format_report


class MapTests(unittest.TestCase):
    def test_ghostty_shaped_graphics_and_iosurface_both_count(self):
        rows=category_rows({'categories':{
            'IOAccelerator (graphics)':{'dirty':766*1048576,'swapped':12*1048576},
            'IOSurface':{'dirty':1768*1048576,'swapped':100*1048576},
            'Owned physical footprint (unmapped) (graphics)':{'dirty':128*1048576,'swapped':0},
            'MALLOC_SMALL':{'dirty':244*1048576}}})
        self.assertEqual(summarize(rows)['graphics_dirty'],(766+1768+128)*1048576)
        self.assertEqual(summarize(rows)['graphics_swapped'],112*1048576)
        self.assertEqual(len(rows),4)
    def test_missing_is_unknown_not_zero(self):
        self.assertIsNone(summarize(category_rows({'categories':{'MALLOC_SMALL':{'dirty':30}}}))['graphics_dirty'])
        self.assertIsNone(summarize(category_rows({'categories':{'IOSurface':{}}}))['graphics_dirty'])
    def test_measured_zero_and_invalid_values(self):
        self.assertEqual(summarize(category_rows({'categories':{'IOSurface':{'dirty':0,'swapped':0}}}))['graphics_dirty'],0)
        self.assertIsNone(valid_int(True));self.assertIsNone(valid_int(-4));self.assertIsNone(valid_int('40'))
    def test_no_double_count_swap_or_rendering(self):
        rows=category_rows({'categories':{'IOSurface':{'dirty':1000,'swapped':600},
                                          'CoreAnimation':{'dirty':3000},'IOAccelerator (graphics)':{'dirty':400}}})
        self.assertEqual(summarize(rows)['graphics_dirty'],1400)
        self.assertIsNone(summarize(rows)['graphics_swapped'])
    def test_output_discloses_scope(self):
        s=format_report({'pid':42,'name':'GPU','status':'ok','rss':123,'categories':[],
                         'summary':{'graphics_categories':0,'all_categories':0,'graphics_dirty':None,'graphics_swapped':None},
                         'vmmap_summary':[],'vmmap_regions':[]})
        self.assertIn('NICHT MESSBAR',s)
        self.assertIn('nicht als 0',s)

if __name__=='__main__':unittest.main()
