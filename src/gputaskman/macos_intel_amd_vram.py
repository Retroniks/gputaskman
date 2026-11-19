"""Verified Intel Radeon IOAccelerator VRAM counters.

vramUsedBytes is a direct *device-wide* counter. Some drivers expose only
vramFreeBytes; that yields total minus free. Both sources can be absent.
No GPU process allocation is inferred from either device counter.
"""
from __future__ import annotations


def _candidates(entries):
    """Find nested performance dictionaries once per enclosing object."""
    seen = set()
    def visit(obj):
        if isinstance(obj, dict):
            stats = obj.get('PerformanceStatistics')
            if isinstance(stats, dict) and id(stats) not in seen:
                seen.add(id(stats))
                yield stats
            for value in obj.values():
                if isinstance(value, (dict, list, tuple)):
                    yield from visit(value)
        elif isinstance(obj, (list, tuple)):
            for child in obj:
                if isinstance(child, (dict, list, tuple)):
                    yield from visit(child)
    yield from visit(entries)


def vram_measurement(entries, total_bytes: int):
    """Return (bytes_used, source). Never resolve conflicting device candidates by guessing."""
    if type(total_bytes) is not int or total_bytes <= 0:
        return None, 'invalid_total'
    direct = set()
    frees = set()
    for stats in _candidates(entries):
        used = stats.get('vramUsedBytes')
        free = stats.get('vramFreeBytes')
        if type(used) is int and 0 <= used <= total_bytes:
            direct.add(used)
        if type(free) is int and 0 <= free <= total_bytes:
            frees.add(free)
    if len(direct) > 1:
        return None, 'ambiguous_vramUsedBytes'
    if len(direct) == 1:
        return next(iter(direct)), 'vramUsedBytes'
    if len(frees) > 1:
        return None, 'ambiguous_vramFreeBytes'
    if len(frees) == 1:
        return total_bytes - next(iter(frees)), 'total_minus_vramFreeBytes'
    return None, 'driver_counter_unavailable'


def vram_used_from_entries(entries, total_bytes: int) -> int | None:
    return vram_measurement(entries, total_bytes)[0]
