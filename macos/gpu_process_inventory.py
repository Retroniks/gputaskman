"""User-facing process inventory: living OS processes, not intermittent GPU clients.
No missing GPU data are invented. Prior measurements are explicitly last-known.
"""
from __future__ import annotations
import time

GPU_FIELDS = ('gpu_pct', 'vram_bytes', 'engines')


class ProcessInventory:
    def __init__(self):
        self.previous_gpu = {}   # (pid,starttime) -> (dict field:value, measured_at)

    def update(self, living, gpu_rows, now=None):
        now = time.monotonic() if now is None else now
        observed = {r['pid']: r for r in gpu_rows if isinstance(r.get('pid'), int)}
        alive_keys = {(p['pid'], p['started_at']) for p in living}
        self.previous_gpu = {k: v for k, v in self.previous_gpu.items() if k in alive_keys}
        output = []
        for p in living:
            pid = p['pid']
            key = (pid, p['started_at'])
            raw = observed.get(pid)
            last, last_time = self.previous_gpu.get(key, ({}, None))
            current = {}
            if raw is not None:
                for field in GPU_FIELDS:
                    if raw.get(field) is not None:
                        current[field] = raw[field]
            if current:
                merged = dict(last, **current)
                self.previous_gpu[key] = (merged, now)
                last = merged
                last_time = now
            result = dict(p)
            result['kind'] = (raw or {}).get('kind') or p.get('kind') or 'process'
            result['gpu_client_observed'] = raw is not None
            result['gpu_measured_at'] = last_time
            result['gpu_value_age_s'] = round(now - last_time, 1) if last_time is not None else None
            for field in GPU_FIELDS:
                # Refresh just the measured fields. All other fields retain last *measured* values.
                result[field] = current.get(field, last.get(field))
            result['gpu_value_state'] = ('current' if current else 'last' if last else 'unavailable')
            output.append(result)
        return output
