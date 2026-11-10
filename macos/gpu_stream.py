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
    from gputaskman.report import to_dict
    sampler = psutil.cpu_percent  # system-wide priming is separate from per-process data
    sampler(interval=None)
    cpu_pids: dict[int, psutil.Process] = {}
    with_collector = Collector(scan_budget=0.0)
    try:
        while True:
            started = time.monotonic()
            snap = with_collector.sample()
            known: dict[int, float] = {}
            for row in snap.procs:
                pid = row.pid
                try:
                    proc = cpu_pids.get(pid)
                    if proc is None or not proc.is_running() or proc.create_time() != row.detail.create_time:
                        proc = psutil.Process(pid)
                        cpu_pids[pid] = proc
                        proc.cpu_percent(interval=None)
                        continue
                    known[pid] = proc.cpu_percent(interval=None)
                except (psutil.Error, OSError):
                    cpu_pids.pop(pid, None)
            cpu_pids = {p: obj for p, obj in cpu_pids.items() if any(x.pid == p for x in snap.procs)}
            data = package(to_dict(snap), known, round((time.monotonic()-started)*1000))
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
