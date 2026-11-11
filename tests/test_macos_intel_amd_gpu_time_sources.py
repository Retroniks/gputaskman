import unittest
from gputaskman.macos import parse_clients

class MacGPUTimeSourceTests(unittest.TestCase):
    def test_direct_gpu_time(self):
        r=parse_clients([{'IOUserClientCreator':'pid 123, Test', 'IORegistryEntryID':17,
                          'accumulatedGPUTime':25_000_000}])
        self.assertEqual(r[123][17],25_000_000)
    def test_app_usage_preferred_no_double_count(self):
        r=parse_clients([{'IOUserClientCreator':'pid 123', 'IORegistryEntryID':17,
                          'accumulatedGPUTime':1_000_000,
                          'AppUsage':[{'accumulatedGPUTime':10_000_000}]}])
        self.assertEqual(r[123][17],10_000_000)
    def test_two_client_slices(self):
        rows=[{'IOUserClientCreator':'pid 99','IORegistryEntryID':1,'accumulatedGPUTime':8},
              {'IOUserClientCreator':'pid 99','IORegistryEntryID':2,
               'AppUsage':[{'accumulatedGPUTime':7},{'accumulatedGPUTime':3}]}]
        self.assertEqual(parse_clients(rows)[99],{1:8,2:10})
    def test_no_gpu_timing_preserves_client(self):
        self.assertEqual(parse_clients([{'IOUserClientCreator':'pid 99','IORegistryEntryID':4}])[99][4],0)
    def test_unrelated_nodes_ignored(self):
        self.assertEqual(parse_clients([{'accumulatedGPUTime':500}]),{})
if __name__=='__main__':
    unittest.main()
