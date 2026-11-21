"""Live per-PID macOS graphics host-memory categories, using real footprint JSON.

These readings are NOT discrete Radeon VRAM. Run footprint outside the UI/sampler
thread. Cache only for a process (pid, creation-time) identity and expire evidence.
"""
from __future__ import annotations

import os
import threading
import time

from gpu_memory_map_040 import category_rows, footprint_for_pid, summarize


def _group_bytes(rows, group):
    values = [r.get('dirty') for r in rows if r.get('group') == group]
    return sum(values) if values and all(v is not None for v in values) else None


def split_graphics_categories(process):
    """Never substitute a missing graphics category with zero."""
    rows = category_rows(process)
    summary = summarize(rows)
    return {
        'graphics_map_bytes': summary['graphics_dirty'],
        'iosurface_bytes': _group_bytes(rows, 'IOSurface'),
        'ioaccelerator_bytes': _group_bytes(rows, 'IOAccelerator'),
        'graphics_ledger_bytes': _group_bytes(rows, 'Grafik-Ledger'),
    }


class LiveGraphicsMemory:
    def __init__(self, fetch=footprint_for_pid, clock=time.monotonic,
                 batch_count=8, interval=8.0, ttl=150.0, start=True):
        self.fetch = fetch
        self.clock = clock
        self.batch_count = max(1, min(batch_count, 12))
        self.interval = interval
        self.ttl = ttl
        self._targets = []
        self._cache = {}
        self._offset = 0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        if start:
            self._thread = threading.Thread(target=self._loop, name='gputaskman-live-memory', daemon=True)
            self._thread.start()

    def set_targets(self, gpu_clients, living):
        """Only actual GPU clients; verify user access in the worker for each PID."""
        starts = {p['pid']: p['started_at'] for p in living
                  if type(p.get('pid')) is int and type(p.get('started_at')) in (float, int)}
        ids = []
        seen = set()
        for row in sorted(gpu_clients, key=lambda r: -(r.get('gpu_pct') or 0)):
            pid = row.get('pid')
            if type(pid) is int and pid > 0 and pid in starts and pid not in seen:
                ids.append((pid, starts[pid]))
                seen.add(pid)
        with self._lock:
            old = self._targets
            self._targets = ids
            alive = set(ids)
            self._cache = {k: v for k, v in self._cache.items() if k in alive}
        if ids and not old:
            self._wake.set()

    def read(self, pid, identity):
        with self._lock:
            hit = self._cache.get((pid, identity))
        if hit is None:
            return None
        stamped, values = hit
        age = max(0.0, self.clock() - stamped)
        if age > self.ttl:
            return None
        return dict(values, graphics_map_age_s=round(age, 1))

    def _measure(self, pid, identity):
        try:
            import psutil
            p = psutil.Process(pid)
            if p.create_time() != identity or (os.geteuid() != 0 and p.uids().real != os.getuid()):
                return None
            process, status = self.fetch(pid)
            if status != 'ok' or process is None:
                result = {'graphics_map_status': status, 'graphics_map_bytes': None,
                          'iosurface_bytes': None, 'ioaccelerator_bytes': None, 'graphics_ledger_bytes': None}
            else:
                result = split_graphics_categories(process)
                result['graphics_map_status'] = 'measured' if result['graphics_map_bytes'] is not None else 'no_graphics_categories'
            if psutil.Process(pid).create_time() != identity:
                return None
            return result
        except (psutil.Error, OSError, ValueError):
            return None

    def _one(self, pid, identity):
        result = self._measure(pid, identity)
        if result is None:
            return
        with self._lock:
            if (pid, identity) in self._targets:
                self._cache[(pid, identity)] = (self.clock(), result)

    def _loop(self):
        while not self._stop.is_set():
            with self._lock:
                targets = list(self._targets)
                start = self._offset % len(targets) if targets else 0
                part = [targets[(start + i) % len(targets)]
                        for i in range(min(len(targets), self.batch_count))]
                self._offset = (start + len(part)) if targets else 0
            for pid, identity in part:
                if self._stop.is_set():
                    break
                self._one(pid, identity)
            self._wake.wait(self.interval)
            self._wake.clear()

    def close(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
