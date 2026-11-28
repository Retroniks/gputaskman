"""Per-process graphics host memory trends. NOT discrete Radeon VRAM."""
from __future__ import annotations

from collections import deque
import math


def _value(x):
    if type(x) is int and x >= 0:
        return x
    if type(x) is float and x >= 0 and math.isfinite(x) and x.is_integer():
        return int(x)
    return None


def compact_extrema(history, limit=64):
    # Preserve actual timestamps, independent extrema and bounding endpoints.
    # This is display decimation, NOT an additional footprint measurement.
    if limit < 4:
        raise ValueError('at least four plot points required')
    readings = list(history)
    if len(readings) <= limit:
        return [[float(t), int(value)] for t, value in readings]
    inside = readings[1:-1]
    buckets = (limit-2)//2
    chosen = [readings[0]]
    for bucket in range(buckets):
        lo = bucket * len(inside) // buckets
        hi = (bucket+1) * len(inside) // buckets
        if lo == hi:
            continue
        minimum = min(range(lo,hi), key=lambda i: inside[i][1])
        maximum = max(range(lo,hi), key=lambda i: inside[i][1])
        for idx in sorted({minimum, maximum}):
            chosen.append(inside[idx])
    chosen.append(readings[-1])
    return [[float(t), int(value)] for t,value in chosen]


class GraphicsTrends:
    """Rolling per-PID 5-minute peak and delta between actual footprint samples.

    A stream snapshot is NOT a new measurement. A newer sample clock is required.
    PID identity includes process creation time to prevent reused-PID contamination.
    """
    def __init__(self, window_s=300.0):
        self.window_s = float(window_s)
        self._history = {}   # (pid, process start) -> deque[(monotonic sample stamp, bytes)]
        self._delta = {}     # same identity -> last actual sample delta

    def update(self, processes, now):
        alive = {(r.get('pid'), r.get('started_at')) for r in processes
                 if type(r.get('pid')) is int and type(r.get('started_at')) in (int, float)}
        for key in list(self._history):
            if key not in alive:
                self._history.pop(key, None)
                self._delta.pop(key, None)
        for row in processes:
            row['graphics_change_bytes'] = None
            row['graphics_peak_5m_bytes'] = None
            row['graphics_trend_samples'] = 0
            row['graphics_series_5m'] = []
            pid, started = row.get('pid'), row.get('started_at')
            key = (pid, started)
            if key not in alive:
                continue
            if row.get('graphics_map_status') != 'measured':
                continue
            value = _value(row.get('graphics_map_bytes'))
            stamp = row.get('graphics_map_sample_clock')
            if value is None or type(stamp) not in (int, float) or not math.isfinite(stamp):
                continue
            stamp = float(stamp)
            if stamp > now + 0.5 or now - stamp > 150.0:
                continue
            hist = self._history.setdefault(key, deque())
            threshold = now - self.window_s
            while hist and hist[0][0] < threshold:
                hist.popleft()
            if hist and stamp > hist[-1][0]:
                self._delta[key] = value - hist[-1][1]
                hist.append((stamp, value))
            elif not hist:
                hist.append((stamp, value))
                self._delta.pop(key, None)
            elif stamp < hist[-1][0]:
                continue  # outdated sample; do not rewind existing history
            # Equal stamp means same reading in another stream frame.
            if hist:
                row['graphics_change_bytes'] = self._delta.get(key)
                row['graphics_peak_5m_bytes'] = max(v for _, v in hist)
                row['graphics_trend_samples'] = len(hist)
                row['graphics_series_5m'] = compact_extrema(hist, limit=64)
