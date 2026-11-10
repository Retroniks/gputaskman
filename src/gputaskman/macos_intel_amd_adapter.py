"""Intel Mac AMD PCI GPU identity from read-only macOS hardware inventory."""
from __future__ import annotations
import json
import platform
import re
import shutil
import subprocess
from functools import lru_cache
from .dxgi import Adapter

VENDOR_AMD = 0x1002


def _vram_bytes(raw: str) -> int:
    text = str(raw or '').replace(',', '.').upper()
    match = re.search(r'([\d.]+)\s*(GB|MB|GIB|MIB)', text)
    if not match:
        return 0
    quantity, unit = float(match.group(1)), match.group(2)
    return int(quantity * (1024 ** 3 if unit in ('GB', 'GIB') else 1024 ** 2))


def from_displays(items: list) -> Adapter | None:
    for display in items:
        name = str(display.get('sppci_model') or display.get('_name') or '')
        vendor = str(display.get('spdisplays_vendor') or '')
        if not ('radeon' in name.lower() or 'amd' in name.lower()):
            continue
        if vendor and 'amd' not in vendor.lower() and '1002' not in vendor.lower():
            continue
        vram = _vram_bytes(display.get('spdisplays_vram') or display.get('spdisplays_vram_shared') or '')
        return Adapter(luid=1, name=name, vendor_id=VENDOR_AMD,
                       dedicated_vram=vram, shared_system=0, software=False)
    return None


@lru_cache(maxsize=1)
def intel_amd_adapter() -> Adapter | None:
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        return None
    try:
        profiler = next((p for p in ('/usr/sbin/system_profiler', '/usr/bin/system_profiler', shutil.which('system_profiler')) if p and __import__('os').access(p, __import__('os').X_OK)), None)
        if profiler is None:
            return None
        output = subprocess.run([profiler, '-json', 'SPDisplaysDataType'],
                                capture_output=True, check=True, timeout=25)
        displays = json.loads(output.stdout).get('SPDisplaysDataType', [])
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return from_displays(displays)
