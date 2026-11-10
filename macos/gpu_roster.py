'Retain living processes with missing GPU readings, but never fabricate live counters.'
import time
class ProcessRoster:
    def __init__(self, ttl=60):
        self.ttl = ttl
        self.entries = {}
    def update(self, rows, identity, now=None):
        now = time.monotonic() if now is None else now
        seen = set()
        for row in rows:
            pid = row.get('pid')
            if not isinstance(pid, int) or pid <= 0: continue
            ident = identity(pid)
            if ident is None: continue
            seen.add(pid)
            self.entries[pid] = (ident, now, dict(row, measurement_state='current'))
        for pid, (original, last, row) in list(self.entries.items()):
            if identity(pid) != original: del self.entries[pid]  # expired GPU samples never imply process exit
        output = []
        for pid, (_, last, row) in self.entries.items():
            r = dict(row)
            if pid not in seen:
                r['measurement_state'] = 'awaiting'
                r['seconds_since_gpu_sample'] = round(now-last, 1)
                for key in ('gpu_pct','cpu_pct','vram_bytes','engines'):
                    r[key] = None
            output.append(r)
        return output
