"""Bounded 32/96 MiB Metal allocation versus real Radeon device VRAM.

Read-only counters; owns and releases only its own tiny native GPU buffers.
No background process or third-party GPU workload is modified.
"""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import plistlib
import select
import subprocess
import sys
import time
from gpu_metal_vram_analysis_036 import comparison, median_valid
from gpu_footprint_category_audit import footprint_details
from gputaskman.macos_intel_amd_adapter import intel_amd_adapter
from gputaskman.macos_intel_amd_vram import vram_used_from_entries
from gputaskman.macos_intel_amd import query_clients
from gputaskman.macos import parse_clients


def device_sample(total_bytes):
    try:
        out = subprocess.run(['/usr/sbin/ioreg', '-a', '-l', '-w', '0', '-c', 'IOAccelerator'],
                             capture_output=True, check=True, timeout=16)
        if not out.stdout:
            return None, 'empty_ioreg'
        value = vram_used_from_entries(plistlib.loads(out.stdout), total_bytes)
        return (value, 'current' if value is not None else 'unavailable_or_ambiguous')
    except (OSError, subprocess.SubprocessError, ValueError, plistlib.InvalidFileException):
        return None, 'ioreg_failed'


def stage_message(process, wanted, timeout=20):
    fd = process.stdout.fileno()
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        raise RuntimeError(f'Metal probe did not report {wanted!r} within {timeout}s')
    line = process.stdout.readline().strip()
    values = line.split('\t')
    if len(values) != 3 or values[0] != 'STAGE' or values[1] != wanted or int(values[2]) != process.pid:
        raise RuntimeError(f'Unexpected native Metal result: {line!r}; expected {wanted}')
    print('METAL_STAGE:', wanted, 'pid=', process.pid, flush=True)


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: script <probe binary> <TSV> <JSON>')
    native, tsv, target = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    adapter = intel_amd_adapter()
    if adapter is None or adapter.vendor_id != 0x1002 or '580' not in adapter.name:
        raise RuntimeError('Verified RX580 Intel macOS GPU unavailable')
    total = int(adapter.dedicated_vram)
    records = []
    by_phase = {}

    def capture(phase, count, pid=None):
        values = []
        for i in range(1, count+1):
            used, state = device_sample(total)
            values.append(used)
            records.append({'phase': phase, 'sample': i, 'timestamp': time.time(),
                            'pid': pid, 'device_vram_used_bytes': used, 'device_read_status': state})
            print(f'[VRAM LIVE] phase={phase} processed={i}/{count} '
                  f'device_vram={used} status={state}', flush=True)
            time.sleep(0.15)
        by_phase[phase] = values

    capture('baseline', 3)
    baseline = median_valid(by_phase['baseline'])
    free = (total-baseline) if baseline is not None else None
    result = {'gpu': adapter.name, 'vram_total_bytes': total,
              'baseline_vram_bytes': baseline, 'free_before_bytes': free,
              'probe_pid': None, 'footprint_32': None, 'footprint_96': None,
              'rx580_gpu_client_at_96': None, 'calibration_status': None,
              'dedicated_vram_per_pid': None}
    if free is None:
        result['calibration_status'] = 'SKIP_DEVICE_COUNTER_UNAVAILABLE'
        print('METAL_CALIBRATION: SKIP device counter unavailable')
    elif free < 384 * 1024 * 1024:
        result['calibration_status'] = 'SKIP_INSUFFICIENT_FREE_VRAM'
        print('METAL_CALIBRATION: SKIP free VRAM below 384 MiB; no allocation performed')
    else:
        process = subprocess.Popen([str(native)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, bufsize=1)
        result['probe_pid'] = process.pid
        try:
            stage_message(process, '32')
            capture('metal_32_mib', 3, process.pid)
            result['footprint_32'] = footprint_details(process.pid)
            process.stdin.write('\n'); process.stdin.flush()
            stage_message(process, '96')
            capture('metal_96_mib', 3, process.pid)
            result['footprint_96'] = footprint_details(process.pid)
            clients = query_clients()
            if clients is not None:
                result['rx580_gpu_client_at_96'] = process.pid in parse_clients(clients)
            process.stdin.write('\n'); process.stdin.flush()
            stage_message(process, 'RELEASE')
            if process.wait(timeout=12) != 0:
                raise RuntimeError(f'Metal process returned {process.returncode}')
            result['calibration_status'] = 'COMPLETED'
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=3)
            process.stdin.close()
            process.stdout.close()
            error = process.stderr.read().strip()
            process.stderr.close()
            if error:
                result['native_stderr'] = error[:1500]
            print('METAL_HELPER_EXIT_CODE:', process.returncode, flush=True)
        capture('released', 3)
    result['calibration'] = comparison(
        by_phase.get('baseline', []),by_phase.get('metal_32_mib', []),
        by_phase.get('metal_96_mib', []),by_phase.get('released', []))
    result['evidence_notes'] = [
        'Metal allocations are known to belong to the helper process, but changes in device VRAM may also include system and concurrent processes.',
        'Graphic footprint on macOS Intel AMD is host memory accounting, not exclusive dedicated VRAM.',
        'Missing or non-responsive device readings are reported unchanged; never fabricated as per-process dedicated VRAM.'
    ]
    result['samples'] = records
    cols=['phase','sample','timestamp','pid','device_vram_used_bytes','device_read_status']
    with tsv.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=cols,delimiter='\t');writer.writeheader();writer.writerows(records)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('CALIBRATION_STATUS:',result['calibration_status'],flush=True)
    print('GPU_TOTAL_BYTES:',total,flush=True)
    print('CALIBRATION_MEDIANS:',result['calibration']['device_vram_medians_bytes'],flush=True)
    print('CALIBRATION_DELTAS:',result['calibration']['device_vram_deltas_from_baseline_bytes'],flush=True)
    print('DEDICATED_VRAM_PER_PID: UNVERIFIED',flush=True)


if __name__ == '__main__':
    main()
