"""Pure comparison of the device-wide RX580 counter across controlled allocations.

The difference includes background processes and driver cache effects. It is
NOT a measurement of per-PID VRAM ownership, and never becomes one in JSON.
"""
from __future__ import annotations
import math
from statistics import median


def median_valid(values):
    accepted = [float(x) for x in values if type(x) in (int, float) and math.isfinite(x) and x >= 0]
    return int(median(accepted)) if accepted else None


def comparison(baseline, phase32, phase96, released):
    med = {k: median_valid(v) for k, v in (
        ('baseline', baseline), ('metal_32_mib', phase32),
        ('metal_96_mib', phase96), ('released', released))}
    ref = med['baseline']
    deltas = {k: (v - ref if v is not None and ref is not None else None)
              for k, v in med.items()}
    return {'device_vram_medians_bytes': med, 'device_vram_deltas_from_baseline_bytes': deltas,
            'staged_device_counter_increase_observed': (deltas['metal_32_mib'] is not None
                                           and deltas['metal_96_mib'] is not None
                                           and deltas['metal_96_mib'] > deltas['metal_32_mib']),
            'attribution': 'controlled-workload temporal association; NOT per-process VRAM ownership'}
