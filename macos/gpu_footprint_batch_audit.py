"""RX580 live group-vs-single footprint audit; no VRAM-per-PID invention."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from gputaskman.collector import Collector
from gputaskman.report import to_dict
from gputaskman.macos import graphics_bytes
from gputaskman.macos_footprint_batch import collect_graphics_batch
from gpu_pid_memory_probe import select_pids


def main():
    tsv, outfile = Path(sys.argv[1]), Path(sys.argv[2])
    collector=Collector(scan_budget=0.0)
    try:
        collector.sample()
        snap=to_dict(collector.sample())
    finally:
        collector.close()
    assert (snap.get('adapter') or {}).get('vendor_id') == 0x1002, 'Expected real AMD Radeon'
    gpu=snap.get('processes') or []
    pids=select_pids(gpu,os.getuid(),max_count=8)
    group=collect_graphics_batch(pids,subprocess.run,graphics_bytes,timeout=20) if len(pids)>1 else None
    rows=[]
    for n,pid in enumerate(pids,1):
        single=collect_graphics_batch([pid],subprocess.run,graphics_bytes,timeout=12)
        gr=group.get(pid) if group is not None else None
        sr=single.get(pid) if single is not None else None
        same=(gr == sr) if gr is not None and sr is not None else None
        rows.append({'pid':pid,'name':next((r.get('name') for r in gpu if r['pid']==pid),''),
                     'single_bytes':sr[0] if sr else None, 'single_status':sr[1] if sr else 'unavailable',
                     'batch_bytes':gr[0] if gr else None, 'batch_status':gr[1] if gr else 'unavailable',
                     'parity': 'match' if same is True else 'mismatch' if same is False else 'unavailable',
                     'dedicated_vram_bytes':None})
        print(f'[PID LIVE] processed={n}/{len(pids)} pct={n*100//max(len(pids),1)} '
              f'pid={pid} grouped={gr} single={sr} parity={same}',flush=True)
    with tsv.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else
                         ['pid','name','single_bytes','single_status','batch_bytes','batch_status','parity','dedicated_vram_bytes'],
                         delimiter='\t');w.writeheader();w.writerows(rows)
    summary={'device_vram_bytes':snap.get('vram_used'),'gpu_client_count':len(gpu),
             'pids_inspected':len(rows),'matching_rows':sum(r['parity']=='match' for r in rows),
             'mismatching_rows':sum(r['parity']=='mismatch' for r in rows),
             'batch_available':group is not None,'dedicated_vram_per_pid_verified':False,'records':rows}
    outfile.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print('GPU_CLIENTS:',len(gpu),flush=True)
    print('BATCH_PARITY:',summary['matching_rows'],'matches',summary['mismatching_rows'],'mismatches',flush=True)
    print('DEVICE_VRAM_BYTES:',summary['device_vram_bytes'],flush=True)
    print('DEDICATED_VRAM_PER_PID: UNVERIFIED',flush=True)

if __name__=='__main__': main()
