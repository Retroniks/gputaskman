"""Offline regression tests for the independent Intel AMD IOKit bridge."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('macos_intel_amd', Path(__file__).resolve().parents[1] / 'src/gputaskman/macos_intel_amd.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_nested():
    item={'IORegistryEntryID': 53, 'IOUserClientCreator':'pid 1262, Firefox GPU', 'AppUsage':[{'accumulatedGPUTime':100}]}
    r=mod.flatten([{'IORegistryEntryChildren':[item]}])
    assert len(r)==1 and r[0] is item

def test_missing():
    assert mod.flatten([{'random':'field'}]) == []

def test_failure():
    class Fail:
        returncode=1
        stdout=b''
    assert mod.query_clients(lambda *a, **k: Fail()) is None

def test_real_format():
    import plistlib
    raw=plistlib.dumps([{'IORegistryEntryID':42,'IOUserClientCreator':'pid 7, test','AppUsage':[{'accumulatedGPUTime':10}]}])
    class Success:
        returncode=0
        stdout=raw
    found=mod.query_clients(lambda *a, **k: Success())
    assert len(found)==1 and found[0]['IORegistryEntryID']==42

if __name__=='__main__':
    test_nested();test_missing();test_failure();test_real_format()
    print('PASS: 4 Intel AMD bridge fixture tests')
