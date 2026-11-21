"""One-source macOS graphics HOST-memory accounting from footprint JSON.

The metrics describe a process's VM categories, not discrete AMD Radeon VRAM.
Missing and zero readings remain distinguishable; no cross-PID summation.
"""
from __future__ import annotations
import math


def _byte(value):
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and math.isfinite(value) and value >= 0 and value.is_integer():
        return int(value)
    return None


def split_graphics_categories(process):
    categories = process.get('categories') if isinstance(process, dict) else None
    result = {'graphics_map_bytes': None, 'iosurface_bytes': None,
              'ioaccelerator_bytes': None, 'graphics_ledger_bytes': None}
    if not isinstance(categories, dict):
        return result
    groups = {'iosurface_bytes': [], 'ioaccelerator_bytes': [], 'graphics_ledger_bytes': []}
    for name, stats in categories.items():
        if not isinstance(name, str) or not isinstance(stats, dict):
            continue
        low = name.lower()
        if 'iosurface' in low:
            group = 'iosurface_bytes'
        elif 'ioaccelerator' in low:
            group = 'ioaccelerator_bytes'
        elif '(graphics)' in low or 'graphics' in low:
            group = 'graphics_ledger_bytes'
        else:
            continue
        groups[group].append(_byte(stats.get('dirty')))
    entries = []
    for key, values in groups.items():
        if values and all(v is not None for v in values):
            result[key] = sum(values)
        entries.extend(values)
    if entries and all(v is not None for v in entries):
        result['graphics_map_bytes'] = sum(entries)
    return result
