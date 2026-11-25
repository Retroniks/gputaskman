"""Persistent GPU snapshots for the native macOS app; one JSON object per line."""
from __future__ import annotations
import json
import os
import sys
import time

def package(snapshot: dict, cpu: dict[int, float], elapsed_ms: int) -> dict:
    processes = []
    for row in snapshot.get("processes") or []:
        if not isinstance(row, dict) or not isinstance(row.get("pid"), int):
            continue
        r = dict(row)
        r["cpu_pct"] = cpu.get(r["pid"])
        processes.append(r)
    snapshot = dict(snapshot)
    snapshot["processes"] = processes
    snapshot["sample_duration_ms"] = elapsed_ms
    return snapshot

def run() -> None:
    import psutil
    from gputaskman.collector import Collector
    from gpu_process_inventory import ProcessInventory
    from gpu_active import active_summary
    from gpu_vram_state import LastVRAM
    from gpu_memory_trends_045 import GraphicsTrends
    from gputaskman.report import to_dict
    import psutil
    psutil.cpu_percent(interval=None)
    inventory = ProcessInventory()
    vram_state = LastVRAM()
    graphics_trends = GraphicsTrends(window_s=300.0)
    cpu_pids = {}
    def enumerate_living():
        living = []
        for p in psutil.process_iter(['pid', 'name', 'create_time', 'status']):
            try:
                info = p.info
                if info['status'] == psutil.STATUS_ZOMBIE:
                    continue
                pid = info['pid']
                started = info['create_time']
                if started is None:
                    continue
                cached = cpu_pids.get(pid)
                if cached is None or cached[0] != started:
                    cpu_pids[pid] = (started, p)
                    p.cpu_percent(interval=None)
                    cpu = None
                else:
                    cpu = p.cpu_percent(interval=None)
                living.append({'pid': pid, 'started_at': started, 'name': info.get('name') or 'PID %s' % pid,
                               'cpu_pct': cpu})
            except (psutil.Error, OSError, KeyError):
                continue
        active = {p['pid'] for p in living}
        for pid in list(cpu_pids):
            if pid not in active:
                del cpu_pids[pid]
        return living
    # Keep the upstream collector's bounded process/runtime/model inspection enabled.
    # 0.0 previously disabled every deep scan in the native UI.
    # Radeon GPU app: bounded source inspection across accessible GPU clients.
    with_collector = Collector(scan_budget=0.35)
    try:
        while True:
            started = time.monotonic()
            snap = with_collector.sample()
            living = enumerate_living()
            raw = vram_state.apply(to_dict(snap))
            observed = raw.get('processes') or []
            raw['processes'] = inventory.update(living, observed)
            # Original metal backend calls the host-RAM graphics footprint vram_bytes.
            # Make the source explicit for the native Intel/AMD UI; per-PID
            # discrete Radeon VRAM remains unmeasured, not zero.
            for process in raw['processes']:
                process['graphics_footprint_bytes'] = process.get('vram_bytes')
                process.update(with_collector.counters.poller.get_graphics_map(process['pid'], process['started_at']) or {})
                process['dedicated_vram_bytes'] = None  # not exposed as proven RX580 bytes per PID
                pid = process['pid']
                if process['graphics_footprint_bytes'] is not None:
                    reason = 'measured' if process.get('gpu_client_observed') else 'last_measured'
                elif not process.get('gpu_client_observed'):
                    reason = 'not_gpu_client'
                else:
                    owner = with_collector.counters._owners.get(pid)
                    if owner is None:
                        reason = 'owner_unavailable'
                    elif owner != os.getuid() and os.geteuid() != 0:
                        reason = 'other_user'
                    else:
                        poller = getattr(with_collector.counters, 'poller', None)
                        reason = poller.status(pid, process['started_at']) if poller and hasattr(poller, 'status') else 'pending'
                process['graphics_footprint_status'] = reason
            graphics_trends.update(raw['processes'], time.monotonic())
            raw['os_process_count'] = len(living)
            raw['gpu_client_count'] = len(observed)
            coverage = with_collector.counters.poller.coverage_snapshot()
            raw['graphics_map_coverage'] = coverage
            raw['graphics_map_measured_count'] = coverage['measured']
            raw['graphics_map_own_gpu_count'] = coverage['total']
            raw['gpu_current_count'] = sum(r['gpu_value_state'] == 'current' for r in raw['processes'])
            raw['gpu_last_count'] = sum(r['gpu_value_state'] == 'last' for r in raw['processes'])
            raw.update(active_summary(raw['processes']))
            raw['sample_duration_ms'] = round((time.monotonic()-started)*1000)
            data = raw
            print(json.dumps(data, separators=(",", ":"), allow_nan=False), flush=True)
            time.sleep(max(0.5, 2.0-(time.monotonic()-started)))
    finally:
        with_collector.close()

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"GPU_STREAM_ERROR {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
