"""Prioritize accessible real GPU processes for the original macOS inspector.

Only reorders genuine collector rows; never invents GPU, model or VRAM data.
The tail rotates so idle apps eventually get inspected, not just the first N.
"""
from __future__ import annotations

AI_HINTS = ('ollama', 'llama', 'whisper', 'pytorch', 'torch', 'python',
            'lm studio', 'comfy', 'diffusion', 'ace-step', 'mlx', 'jan.ai')


def prioritize_radeon_processes(rows, owners, uid, cycle):
    mine = [r for r in rows if owners.get(r.pid) == uid and not r.detail.access_denied]
    others = [r for r in rows if r not in mine]
    active = sorted((r for r in mine if r.gpu.gpu_pct > 0),
                    key=lambda r: (-r.gpu.gpu_pct, r.pid))
    selected = {r.pid for r in active}
    ai = [r for r in mine if r.pid not in selected
          and any(keyword in r.name.lower() for keyword in AI_HINTS)]
    selected.update(r.pid for r in ai)
    idle = [r for r in mine if r.pid not in selected]
    if idle:
        shift = (int(cycle) * 11) % len(idle)
        idle = idle[shift:] + idle[:shift]
    return active + ai + idle + others
