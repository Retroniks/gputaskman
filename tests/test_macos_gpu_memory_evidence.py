import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'macos'))
from gpu_memory_evidence import summarize

class MemoryEvidenceTests(unittest.TestCase):
    def test_numeric_client_field_is_only_candidate(self):
        nodes=[{'IOUserClientCreator':'pid 42, client','vramAllocatedBytes':123}]
        pids,keys,owners=summarize(nodes)
        self.assertEqual(pids,{42})
        self.assertEqual(keys[('vramAllocatedBytes','number')],1)
        self.assertEqual(owners[(42,'vramAllocatedBytes')],1)
    def test_no_pid_no_attribution(self):
        pids,keys,owners=summarize([{'vramAllocatedBytes':123}])
        self.assertFalse(pids or keys or owners)
    def test_non_numeric_ignored(self):
        _,keys,_=summarize([{'IOUserClientCreator':'pid 42','memory':'unknown'}])
        self.assertFalse(keys)
    def test_nested_client_field(self):
        _,keys,_=summarize([{'IOUserClientCreator':'pid 11','PerformanceStatistics':{'vramFreeBytes':100}}])
        self.assertEqual(keys[('PerformanceStatistics.vramFreeBytes','number')],1)
    def test_no_pid_creation_from_unlinked_child(self):
        _,keys,_=summarize([{'IOUserClientCreator':'pid 12','child':{'vramUsedBytes':20}}])
        self.assertFalse(keys) # no implied linkage of nested independent nodes
if __name__=='__main__':unittest.main()
