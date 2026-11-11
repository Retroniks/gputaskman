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
    from gputaskman.report import to_dict
    import psutil
    psutil.cpu_percent(interval=None)
    inventory = ProcessInventory()
    vram_state = LastVRAM()
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
    with_collector = Collector(scan_budget=0.0)
    try:
        while True:
            started = time.monotonic()
            snap = with_collector.sample()
            living = enumerate_living()
            raw = vram_state.apply(to_dict(snap))
            observed = raw.get('processes') or []
            raw['processes'] = inventory.update(living, observed)
            raw['os_process_count'] = len(living)
            raw['gpu_client_count'] = len(observed)
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
