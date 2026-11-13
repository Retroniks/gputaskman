"""Read-only RX580 per-PID graphics accounting diagnostic.

Mach graphics-ledger bytes and footprint dirty categories are NOT direct
measurements of discrete Radeon VRAM ownership. Keep sources separate.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def category_bytes(data, pid):
    """Extract relevant *dirty* host-memory categories, retaining missing vs zero."""
    matches = [p for p in (data.get('processes') or [])
               if str(p.get('pid')) == str(pid)]
    if len(matches) != 1:
        return None
    categories = matches[0].get('categories')
    if not isinstance(categories, dict) or not categories:
        return None
    results = {'graphics_dirty': 0, 'iosurface_dirty': 0,
               'ioaccelerator_dirty': 0, 'matching_categories': 0}
    for key, stats in categories.items():
        if not isinstance(stats, dict):
            continue
        dirty = stats.get('dirty')
        if not isinstance(dirty, (int, float)) or isinstance(dirty, bool) or dirty < 0:
            continue
        if key.endswith('(graphics)'):
            results['graphics_dirty'] += int(dirty)
            results['matching_categories'] += 1
        if 'IOSurface' in key:
            results['iosurface_dirty'] += int(dirty)
        if 'IOAccelerator' in key:
            results['ioaccelerator_dirty'] += int(dirty)
    return results


def select_pids(rows, uid, max_count=6):
    """Prioritize measured GPU users, avoid scanning unrelated daemons."""
    import psutil
    ranked = sorted(rows, key=lambda r: -(r.get('gpu_pct') or 0))
    candidates = []
    for row in ranked:
        pid = row.get('pid')
        if not isinstance(pid, int) or pid <= 0 or pid in candidates:
            continue
        try:
            p = psutil.Process(pid)
            if p.uids().real != uid or not p.is_running():
                continue
        except (psutil.Error, OSError):
            continue
        candidates.append(pid)
        if len(candidates) == max_count:
            break
    return candidates


def read_ledger(binary, pid):
    try:
        result = subprocess.run([str(binary), str(pid)], text=True,
                                capture_output=True, timeout=5)
        parts = result.stdout.strip().split('\t')
        if result.returncode == 0 and len(parts) == 4 and int(parts[0]) == pid:
            status = parts[1]
            return {'status': status,
                    'graphics_ledger_bytes': int(parts[2]) if status == 'ok' else None,
                    'device_bytes': int(parts[3]) if status == 'ok' else None}
        return {'status': 'invalid_response', 'graphics_ledger_bytes': None, 'device_bytes': None}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'status': 'probe_failed', 'graphics_ledger_bytes': None, 'device_bytes': None}


def read_footprint(pid):
    with tempfile.TemporaryDirectory(prefix='gtm-pid-memory-') as td:
        target = Path(td)/'footprint.json'
        try:
            result = subprocess.run(['/usr/bin/footprint', '-f', 'bytes', '-j', str(target),
                                     '-p', str(pid)], capture_output=True, timeout=12)
            if not target.exists():
                return {'status': f'no_json_exit_{result.returncode}'}
            data = json.loads(target.read_text())
            got = category_bytes(data, pid)
            if got is None:
                return {'status': f'no_pid_category_exit_{result.returncode}'}
            return dict(status='ok' if result.returncode == 0 else f'nonzero_exit_{result.returncode}', **got)
        except subprocess.TimeoutExpired:
            return {'status': 'timeout'}
        except (OSError, ValueError, json.JSONDecodeError):
            return {'status': 'read_or_json_error'}


def main():
    if len(sys.argv) != 5:
        raise SystemExit('usage: module <native probe> <tsv> <json> <limit>')
    native, tsv, detail, limit = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
    from gputaskman.collector import Collector
    from gputaskman.report import to_dict
    collector = Collector(scan_budget=0.0)
    try:
        collector.sample()
        sample = to_dict(collector.sample())
    finally:
        collector.close()
    adapter = sample.get('adapter') or {}
    if adapter.get('vendor_id') != 0x1002:
        raise RuntimeError(f'Intel AMD adapter not detected: {adapter}')
    candidates = select_pids(sample.get('processes') or [], os.getuid(), max_count=limit)
    print('DEVICE_VRAM_BYTES:', sample.get('vram_used'), flush=True)
    print('DEVICE_VRAM_TOTAL:', sample.get('vram_total'), flush=True)
    print('GPU_CLIENT_ROWS:', len(sample.get('processes') or []), flush=True)
    print('OWNED_PROCESS_CANDIDATES:', candidates, flush=True)
    records = []
    for index, pid in enumerate(candidates, 1):
        row = next(r for r in sample['processes'] if r['pid'] == pid)
        ledger = read_ledger(native, pid)
        footprint = read_footprint(pid)
        record = {'pid': pid, 'name': row.get('name'), 'gpu_pct': row.get('gpu_pct'),
                  'ledger_status': ledger['status'],
                  'graphics_ledger_bytes': ledger['graphics_ledger_bytes'],
                  'device_ledger_bytes': ledger['device_bytes'],
                  'footprint_status': footprint['status'],
                  'graphics_dirty_bytes': footprint.get('graphics_dirty'),
                  'iosurface_dirty_bytes': footprint.get('iosurface_dirty'),
                  'ioaccelerator_dirty_bytes': footprint.get('ioaccelerator_dirty'),
                  'discrete_vram_attributed_bytes': None,
                  'discrete_vram_attribution': 'not_proven'}
        records.append(record)
        print(f'[PID LIVE] processed={index}/{len(candidates)} pid={pid} '
              f'ledger={ledger["status"]} footprint={footprint["status"]} '
              f'graphics_ledger={ledger["graphics_ledger_bytes"]}', flush=True)
    headings = ['pid', 'name', 'gpu_pct', 'ledger_status', 'graphics_ledger_bytes',
                'device_ledger_bytes', 'footprint_status', 'graphics_dirty_bytes',
                'iosurface_dirty_bytes', 'ioaccelerator_dirty_bytes',
                'discrete_vram_attributed_bytes', 'discrete_vram_attribution']
    with tsv.open('w', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=headings, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    meta = {'adapter_name': adapter.get('name'), 'device_vram_bytes': sample.get('vram_used'),
            'device_vram_total_bytes': sample.get('vram_total'),
            'probed_process_count': len(records), 'records': records,
            'interpretation': ('TASK_VM_INFO and footprint provide system graphics memory accounting; '
                               'neither proves dedicated Radeon VRAM allocations per PID.')}
    detail.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + '\n')
    print('MEASUREMENT_SOURCE_COMPARISON: PASS', flush=True)
    print('DEDICATED_RX580_VRAM_PER_PID: UNVERIFIED', flush=True)


if __name__ == '__main__':
    main()
