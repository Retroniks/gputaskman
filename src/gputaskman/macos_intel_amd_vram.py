"""Discrete Radeon VRAM counters exposed by IOAccelerator on Intel macOS.

vramFreeBytes is GPU VRAM, not GART/GTT. Prefer PerformanceStatistics
and refuse ambiguous or out-of-range readings. No made-up zero readings.
"""
from __future__ import annotations


def vram_used_from_entries(entries, total_bytes: int) -> int | None:
    if not isinstance(total_bytes, int) or total_bytes <= 0:
        return None
    readings = []
    def visit(obj):
        if isinstance(obj, dict):
            stats = obj.get('PerformanceStatistics')
            if isinstance(stats, dict):
                free = stats.get('vramFreeBytes')
                if type(free) is int and 0 <= free <= total_bytes:
                    readings.append(free)
            for child in obj.values():
                if isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(obj, list):
            for child in obj:
                if isinstance(child, (dict, list)):
                    visit(child)
    visit(entries)
    if not readings:
        return None
    # Duplicated snapshots of one counter may be present in nested IORegistry nodes.
    # Distinct readings are ambiguous (multiple devices or non-atomic samples).
    if len(set(readings)) != 1:
        return None
    return total_bytes - readings[0]
