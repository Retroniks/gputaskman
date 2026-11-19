"""Read-only native macOS GPU process memory map (footprint + vmmap).

No part of this module converts graphics footprint into discrete Radeon VRAM.
Each category is reported once. The `swapped` amount is a SUBSET of dirty,
never added to dirty. vmmap values are shown as separate evidence, not added.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

GPU_RE = re.compile(r'graphics|ioaccelerator|iosurface', re.IGNORECASE)
RENDER_RE = re.compile(r'coreanimation|cg image|imageio', re.IGNORECASE)
VM_RE = re.compile(r'iosurface|ioaccelerator|\(graphics\)|metal|physical footprint|^\s*total\b', re.IGNORECASE)
REGION_RE = re.compile(r'^\s*(?:IOAccelerator|IOSurface|(?:.*\(graphics\)))\s+0x[0-9a-fA-F]+', re.IGNORECASE)


def valid_int(value):
    """Footprint JSON bytes must be finite and nonnegative, not booleans or strings."""
    if type(value) is int:
        return value if value >= 0 else None
    if type(value) is float and value >= 0 and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def kind_for(name):
    """Keep charged graphics and rendering-adjacent memory distinct."""
    low = name.lower()
    if 'iosurface' in low:
        return 'IOSurface'
    if 'ioaccelerator' in low:
        return 'IOAccelerator'
    if '(graphics)' in low or 'graphics' in low:
        return 'Grafik-Ledger'
    if RENDER_RE.search(low):
        return 'Rendering (separat)'
    return 'Andere'


def category_rows(process):
    cats = process.get('categories') if isinstance(process, dict) else None
    if not isinstance(cats, dict):
        return []
    fields = ('dirty', 'clean', 'reclaimable', 'swapped', 'wired', 'regions')
    rows = []
    for name, stats in cats.items():
        if not isinstance(name, str) or not isinstance(stats, dict):
            continue
        row = {'category': name, 'group': kind_for(name)}
        row.update({field: valid_int(stats.get(field)) for field in fields})
        rows.append(row)
    rows.sort(key=lambda r: (-(r['dirty'] if r['dirty'] is not None else -1), r['category'].lower()))
    return rows


def summarize(rows):
    """Independent footprint category sums, *not* additive across PID owners."""
    groups = ('IOSurface', 'IOAccelerator', 'Grafik-Ledger')
    selected = [r for r in rows if r['group'] in groups]
    dirty = [r['dirty'] for r in selected if r['dirty'] is not None]
    # Unknown is NOT zero if category read exists but its dirty byte count is invalid.
    graphics_dirty = sum(dirty) if dirty and len(dirty) == len(selected) else None
    swapped = [r['swapped'] for r in selected if r['swapped'] is not None]
    graphics_swapped = sum(swapped) if selected and len(swapped) == len(selected) else None
    return {'graphics_dirty': graphics_dirty, 'graphics_swapped': graphics_swapped,
            'graphics_categories': len(selected), 'all_categories': len(rows),
            'rendering_categories': len([r for r in rows if r['group'] == 'Rendering (separat)'])}


def mib(value):
    return '—' if value is None else f'{value / 1048576:,.2f} MiB'


def _exec(command, timeout):
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, '', 'Zeitlimit'
    except OSError as ex:
        return 127, '', str(ex)


def footprint_for_pid(pid, timeout=10):
    with tempfile.TemporaryDirectory(prefix='gtm-map-') as tmp:
        dest = str(Path(tmp) / 'footprint.json')
        ret, _text, err = _exec(['/usr/bin/footprint', '-f', 'bytes', '-j', dest, '-p', str(pid)], timeout)
        if not os.path.isfile(dest):
            return None, f'footprint_kein_JSON (exit {ret}: {err.strip()[:100]})'
        try:
            data = json.loads(Path(dest).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None, 'footprint_JSON_unlesbar'
    found = [p for p in data.get('processes', []) if isinstance(p, dict) and str(p.get('pid')) == str(pid)]
    if len(found) != 1:
        return None, f'footprint_PID_nicht_eindeutig (exit {ret})'
    if ret != 0:
        return found[0], f'footprint_exit_{ret}'
    return found[0], 'ok'


def vmmap_evidence(pid, full):
    ret, out, err = _exec(['/usr/bin/vmmap', '-summary', str(pid)], 12)
    if ret != 0:
        summary = [f'vmmap -summary: nicht verfügbar (exit {ret}: {err.strip()[:100]})']
    else:
        # Raw vmmap lines retain the original virtual/resident/dirty/swapped columns.
        summary = [line.rstrip() for line in out.splitlines() if VM_RE.search(line)][:40]
        if not summary:
            summary = ['vmmap -summary: keine eindeutigen Grafikzeilen']
    region = []
    if full:
        ret, out, err = _exec(['/usr/bin/vmmap', str(pid)], 12)
        if ret == 0:
            region = [line.rstrip() for line in out.splitlines() if GPU_RE.search(line) and '0x' in line][:35]
            if not region:
                region = ['vmmap: keine zuordenbaren Einzelregionen']
        else:
            region = [f'vmmap-Regionen: nicht verfügbar (exit {ret}: {err.strip()[:100]})']
    return summary, region


def inspect_pid(pid, full=False, with_vmmap=True):
    import psutil
    if type(pid) is not int or pid <= 0:
        return {'pid': pid, 'status': 'ungueltige_PID'}
    try:
        process = psutil.Process(pid)
        owner = process.uids().real
        start = process.create_time()
        name = process.name()
        resident = process.memory_info().rss
    except (psutil.Error, OSError) as exc:
        return {'pid': pid, 'status': f'Prozess_nicht_zugaenglich ({type(exc).__name__})'}
    if owner != os.getuid() and os.geteuid() != 0:
        return {'pid': pid, 'name': name, 'status': 'anderer_Benutzer_ohne_root'}
    fp, status = footprint_for_pid(pid)
    rows = category_rows(fp)
    summary = summarize(rows)
    vm_summary, vm_regions = vmmap_evidence(pid, full) if with_vmmap else ([], [])
    try:
        current = psutil.Process(pid)
        if current.create_time() != start:
            return {'pid': pid, 'name': name, 'status': 'PID_neu_vergeben'}
    except (psutil.Error, OSError):
        return {'pid': pid, 'name': name, 'status': 'Prozess_beendet'}
    return {'pid': pid, 'name': name, 'status': status, 'owner': owner, 'rss': resident,
            'categories': rows, 'summary': summary,
            'vmmap_summary': vm_summary, 'vmmap_regions': vm_regions}


def format_report(info):
    pid, name = info.get('pid'), info.get('name', '?')
    lines = [f'PID {pid}   {name}', f'STATUS: {info.get("status")}']
    if 'summary' not in info:
        lines.append('Grafik-Speicher: nicht ermittelbar – kein Nullwert.'); return '\n'.join(lines)
    s = info['summary']
    lines.extend([
        f'Prozess-RSS: {mib(info.get("rss"))} (gesamter Resident Set, kein GPU-VRAM)',
        f'Grafik-Kategorien: {s["graphics_categories"]} von {s["all_categories"]}',
        f'Grafik-dirty/Footprint-Anteile: {mib(s["graphics_dirty"])} (macOS-Hostspeicherabrechnung)',
        f'Grafik-swapped (Teilmenge dirty): {mib(s["graphics_swapped"])}',
        'Dedizierter RX-580-VRAM dieses Prozesses: NICHT MESSBAR MIT DIESEN QUELLEN',
        'KATEGORIEN (dirty enthält swapped; Spalten NICHT addieren):',
        'DIRTY MiB | CLEAN MiB | RECLAIM MiB | SWAPPED MiB | WIRED MiB | REGIONS | KATEGORIE',
    ])
    for r in info['categories']:
        if r['group'] == 'Andere':
            continue
        fields = [f'{r[k] / 1048576:.2f}' if r[k] is not None else '—'
                  for k in ('dirty', 'clean', 'reclaimable', 'swapped', 'wired')]
        lines.append(' | '.join(fields + [str(r['regions']) if r['regions'] is not None else '—', r['category']]))
    if not any(r['group'] != 'Andere' for r in info['categories']):
        lines.append('Keine Grafik-/Renderingkategorien erfasst (nicht als 0 interpretieren).')
    if info['vmmap_summary']:
        lines.extend(['VMMAP-SUMMARY (Rohwerte, separat; NICHT zu footprint addieren):', *info['vmmap_summary']])
    if info['vmmap_regions']:
        lines.extend(['VMMAP-EINZELREGIONEN (maximal 35 Zeilen):', *info['vmmap_regions']])
    return '\n'.join(lines)


def scan(limit):
    from gputaskman.collector import Collector
    from gputaskman.report import to_dict
    from gpu_pid_memory_probe import select_pids
    collector = Collector(scan_budget=0.0)
    try:
        collector.sample()
        snapshot = to_dict(collector.sample())
    finally:
        collector.close()
    adapter = snapshot.get('adapter') or {}
    if adapter.get('vendor_id') != 0x1002:
        raise RuntimeError('AMD Radeon nicht erkannt – kein falscher Hardware-PASS')
    gpu = snapshot.get('processes') or []
    pids = select_pids(gpu, os.getuid(), max_count=limit)
    print(f'GPU: {adapter.get("name")} | GPU-Clients: {len(gpu)} | eigene Kandidaten: {len(pids)}', flush=True)
    print('Gesamt-VRAM: ' + mib(snapshot.get('vram_used')) + ' von ' + mib(snapshot.get('vram_total')),flush=True)
    print('Diese Gesamtbelegung wird NICHT auf PIDs verteilt. Keine nachträgliche Schätzung.',flush=True)
    print('---')
    good = 0
    for i, pid in enumerate(pids, 1):
        # Summary + raw VM regions only on first 3 active/accessible GPUs; can be loaded for any PID in GUI.
        entry = inspect_pid(pid, full=(i <= 3), with_vmmap=(i <= 3))
        good += entry.get('summary', {}).get('graphics_dirty') is not None
        print(f'[LIVE PID] processed={i}/{len(pids)} pct={i*100//max(len(pids),1)} '
              f'pid={pid} graphic_dirty={entry.get("summary",{}).get("graphics_dirty")} '
              f'status={entry.get("status")}', flush=True)
        print(format_report(entry), flush=True)
        print('---',flush=True)
    print(f'ERGEBNIS: {good}/{len(pids)} ausgewählte Prozesse mit nachgewiesenem Grafik-dirty-Wert',flush=True)
    print('Jeder Kategorieeintrag ist direkt aus footprint und/oder vmmap; kein dedizierter VRAM pro PID.',flush=True)
    if not pids or good == 0:
        raise RuntimeError('Keine belastbare GPU-Memory-Map von dieser Hardwaremessung erhalten')


def main():
    parser = argparse.ArgumentParser(description='Read-only GPU memory mapping per PID')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pid', type=int)
    group.add_argument('--scan', type=int)
    options = parser.parse_args()
    if options.pid is not None:
        print(format_report(inspect_pid(options.pid, full=True)), flush=True)
    else:
        if not 1 <= options.scan <= 24:
            parser.error('--scan zwischen 1 und 24')
        scan(options.scan)


if __name__ == '__main__':
    main()
