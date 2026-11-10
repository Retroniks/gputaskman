"""Offline fixture tests for Intel/AMD IORegistry client discovery."""
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'tools' / 'macos_intel_amd_clients.py'
spec = importlib.util.spec_from_file_location('macos_intel_amd_clients', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_nested_client():
    data = [{'IOClass': 'IOAccelerator', 'IORegistryEntryChildren': [
        {'IOClass': 'IOAccelUserClient', 'IORegistryEntryID': 55,
         'IOUserClientCreator': 'pid 1262, Firefox GPU Helper',
         'AppUsage': [{'accumulatedGPUTime': 120}, {'accumulatedGPUTime': 30}]}]}]
    result = mod.collect(data)
    assert result['per_pid_time_ns']['1262']['55'] == 150
    assert result['creator_nodes'] == 1


def test_missing_time_is_unknown():
    result = mod.collect([{'IOUserClientCreator': 'pid 42, Some App'}])
    assert result['time_fields'] == 0
    assert result['per_pid_time_ns'] == {}


def test_unattached_time_not_misassigned():
    result = mod.collect([{'accumulatedGPUTime': 100}])
    assert result['unattached_time_fields'] == 1
    assert result['per_pid_time_ns'] == {}


if __name__ == '__main__':
    test_nested_client()
    test_missing_time_is_unknown()
    test_unattached_time_not_misassigned()
    print('PASS: 3 Intel AMD fixture tests')
