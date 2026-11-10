"""Read-only macOS Intel/AMD GPU client discovery.

Distinguishes IORegistry device statistics from GPU user clients. Unknown
or unsupported per-process metrics remain None; no fabricated zero values.
"""
from __future__ import annotations
import json
import plistlib
import re
import subprocess
import time
from collections import defaultdict

PID = re.compile(r"\bpid\s+(\d+)\b", re.I)


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from walk(value)


def collect(data):
    nodes = list(walk(data))
    classes = defaultdict(int)
    creators = defaultdict(int)
    gpu_times = defaultdict(dict)
    any_times = 0
    orphan_times = 0
    for index, node in enumerate(nodes):
        cls = node.get('IOClass') or node.get('IOObjectClass')
        if isinstance(cls, str):
            classes[cls] += 1
        creator = node.get('IOUserClientCreator')
        match = PID.search(creator) if isinstance(creator, str) else None
        if match:
            creators[match.group(1)] += 1
        usages = node.get('AppUsage')
        times = []
        if isinstance(usages, (list, tuple)):
            for usage in usages:
                if isinstance(usage, dict) and isinstance(usage.get('accumulatedGPUTime'), (int, float)):
                    times.append(int(usage['accumulatedGPUTime']))
        if isinstance(node.get('accumulatedGPUTime'), (int, float)):
            times.append(int(node['accumulatedGPUTime']))
        any_times += len(times)
        if not match and times:
            orphan_times += len(times)
        if match and times:
            key = str(node.get('IORegistryEntryID', index))
            gpu_times[match.group(1)][key] = sum(times)
    perf = [node['PerformanceStatistics'] for node in nodes
            if isinstance(node.get('PerformanceStatistics'), dict)]
    return {
        'node_count': len(nodes), 'creator_nodes': sum(creators.values()),
        'creator_pid_count': len(creators), 'creator_pids': dict(sorted(creators.items())),
        'time_fields': any_times, 'unattached_time_fields': orphan_times,
        'per_pid_time_ns': dict(gpu_times),
        'performance_sets': len(perf),
        'device_utilization_values': [p.get('Device Utilization %') for p in perf],
        'interesting_classes': {k: v for k, v in classes.items()
                                if 'GPU' in k.upper() or 'ACCEL' in k.upper() or 'CLIENT' in k.upper()},
    }


def query(*flags):
    cmd = ['/usr/sbin/ioreg', '-a', '-l', '-w', '0', *flags]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if p.returncode:
        return None, 'ioreg returned {}'.format(p.returncode)
    try:
        return plistlib.loads(p.stdout), None
    except (ValueError, plistlib.InvalidFileException) as e:
        return None, '{}: {}'.format(type(e).__name__, e)


def run():
    results = []
    for number in range(2):
        sources = {}
        for label, flags in [('accelerator_tree', ('-c', 'IOAccelerator')),
                             ('userclient_tree', ('-c', 'IOUserClient'))]:
            data, error = query(*flags)
            if error:
                sources[label] = {'error': error}
            else:
                sources[label] = collect(data)
        results.append({'at_ns': time.monotonic_ns(), 'sources': sources})
        if number == 0:
            time.sleep(1.2)
    delta = (results[1]['at_ns'] - results[0]['at_ns']) / 1e9
    process_rate = {}
    for label in ('accelerator_tree', 'userclient_tree'):
        old = results[0]['sources'][label].get('per_pid_time_ns', {})
        new = results[1]['sources'][label].get('per_pid_time_ns', {})
        rates = {}
        for pid, clients in new.items():
            before = old.get(pid, {})
            matched = clients.keys() & before.keys()
            if matched:
                growth = sum(max(0, clients[c] - before[c]) for c in matched)
                rates[pid] = round(100 * growth / (delta * 1e9), 3)
        process_rate[label] = rates
    return {'schema': 2, 'target': 'macos-intel-amd', 'elapsed_seconds': round(delta, 4),
            'samples': results, 'matched_process_gpu_percent': process_rate,
            'interpretation': 'Device statistics and client timing are separately evidenced; no rate is inferred without matching client IDs.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
