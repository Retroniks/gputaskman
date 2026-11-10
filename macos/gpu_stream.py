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
    from gpu_roster import ProcessRoster
    from gputaskman.report import to_dict
    sampler = psutil.cpu_percent  # system-wide priming is separate from per-process data
    sampler(interval=None)
    cpu_pids: dict[int, psutil.Process] = {}
    roster = ProcessRoster(ttl=60)
    def process_identity(pid):
        try:
            p = psutil.Process(pid)
            return p.create_time() if p.is_running() and p.status() != psutil.STATUS_ZOMBIE else None
        except (psutil.Error, OSError):
            return None
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
            raw = data["processes"]
            data["observed_process_count"] = len(raw)
            data["processes"] = roster.update(raw, process_identity)
            data["awaiting_process_count"] = sum(r["measurement_state"] == "awaiting" for r in data["processes"])
            data["roster_process_count"] = len(data["processes"])
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
