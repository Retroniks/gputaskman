"""Read multiple own-PID graphics *host RAM* footprints in one footprint(1) call.

These bytes never prove ownership of discrete Radeon VRAM. `None` is an
unavailable reading; a measured zero is preserved. A malformed/incomplete
batch is rejected in full and can be retried as individual measurements.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


def collect_graphics_batch(pids, run, extractor: Callable, timeout=18):
    ordered = list(dict.fromkeys(pids))
    if not ordered or any(type(p) is not int or p <= 0 for p in ordered):
        return None
    with tempfile.TemporaryDirectory(prefix='gtm-footprint-batch-') as tmp:
        target = Path(tmp) / 'footprint.json'
        cmd = ['/usr/bin/footprint', '-f', 'bytes', '-j', str(target)]
        for pid in ordered:
            cmd.extend(('-p', str(pid)))
        try:
            completed = run(cmd, capture_output=True, timeout=timeout)
            if not target.is_file() or target.stat().st_size == 0:
                return None
            data = json.loads(target.read_text(encoding='utf-8'))
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    rows = data.get('processes') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    expected = set(ordered)
    actual = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = row.get('pid')
        if type(pid) is not int or pid not in expected or pid in actual:
            continue
        value = extractor(row)
        if value is not None and (type(value) not in (int, float) or value < 0 or not math.isfinite(value)):
            return None
        actual[pid] = (None if value is None else int(value),
                       'no_graphics_categories' if value is None else 'measured')
    # Do not silently relabel a missing PID as having no graphics allocations.
    # PID exits, protection failures and bad JSON all go to the single-PID path.
    if set(actual) != expected:
        return None
    return actual
