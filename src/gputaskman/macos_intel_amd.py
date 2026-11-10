"""Intel macOS Radeon GPU IORegistry reader, using the original MacCounters data shape.

Requires an IOAccelerator subtree rather than AGXDeviceUserClient (Apple Silicon).
The source is read-only. Unknown device statistics remain unknown.
"""
from __future__ import annotations
import os
import plistlib
import subprocess


def is_intel_amd() -> bool:
    if os.uname().machine != 'x86_64':
        return False
    try:
        result = subprocess.run(['/usr/sbin/system_profiler', 'SPDisplaysDataType'],
                                text=True, capture_output=True, timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = result.stdout.lower()
    return 'amd radeon' in text or 'radeon rx' in text


def flatten(data):
    """Preserve each IOKit object exactly once, including nested GPU client nodes."""
    found = []
    def visit(value):
        if isinstance(value, dict):
            if 'IORegistryEntryID' in value or 'IOUserClientCreator' in value or 'PerformanceStatistics' in value:
                found.append(value)
            for child in value.values():
                if isinstance(child, (list, tuple, dict)):
                    visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(data)
    return found


def query_clients(run=subprocess.run):
    """Returns flattened clients, or None on query failure (not an empty success)."""
    try:
        proc = run(['/usr/sbin/ioreg', '-a', '-l', '-w', '0', '-c', 'IOAccelerator'],
                   capture_output=True, timeout=18)
        if proc.returncode or not proc.stdout.strip():
            return None
        return flatten(plistlib.loads(proc.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, plistlib.InvalidFileException):
        return None
