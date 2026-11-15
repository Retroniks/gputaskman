"""Bounded read-only real Radeon process footprint diagnostic with explicit gaps."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import sys
import psutil
from gputaskman.collector import Collector
from gputaskman.report import to_dict
from gpu_pid_memory_probe import select_pids
from gpu_footprint_category_audit import footprint_details


def main():
    tsv, outfile, limit = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    collector=Collector(scan_budget=0.0)
    try:
        collector.sample()
        sample=to_dict(collector.sample())
    finally:
        collector.close()
    if (sample.get('adapter') or {}).get('vendor_id') != 0x1002:
        raise RuntimeError('AMD Radeon adapter absent')
    gpurows=sample.get('processes') or []
    pids=select_pids(gpurows,os.getuid(),max_count=limit)
    allowners={'mine':0,'other_user':0,'uid_unavailable':0}
    for row in gpurows:
        try:
            uid=psutil.Process(row['pid']).uids().real
            allowners['mine' if uid==os.getuid() else 'other_user']+=1
        except (psutil.Error,OSError):
            allowners['uid_unavailable']+=1
    records=[]
    for index,pid in enumerate(pids,1):
        entry=next(r for r in gpurows if r['pid']==pid)
        details=footprint_details(pid)
        amount=details['bytes']
        reason=('measured' if amount is not None else
                'no_graphics_categories' if details['status']=='ok' else details['status'])
        records.append({'pid':pid,'name':entry.get('name'),'gpu_pct':entry.get('gpu_pct'),
                        'reason':reason,'footprint_bytes':amount,
                        'category_basis':details['basis'],
                        'categories':';'.join(details['categories']),
                        'dedicated_vram_bytes':None})
        print(f'[PID LIVE] processed={index}/{len(pids)} pct={index*100//len(pids)} '
              f'pid={pid} reason={reason} graphics_host_ram={amount}',flush=True)
    headers=['pid','name','gpu_pct','reason','footprint_bytes','category_basis','categories','dedicated_vram_bytes']
    with tsv.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers,delimiter='\t')
        writer.writeheader(); writer.writerows(records)
    reasons={}
    for row in records:
        reasons[row['reason']]=reasons.get(row['reason'],0)+1
    summary={'device_vram_bytes':sample.get('vram_used'),
             'device_total_bytes':sample.get('vram_total'),
             'gpu_client_count':len(gpurows),'gpu_client_owners':allowners,
             'inspected_own_pids':len(records),'reason_counts':reasons,
             'per_pid_dedicated_vram_verified':False,'rows':records}
    outfile.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('DEVICE_VRAM_BYTES:',summary['device_vram_bytes'],flush=True)
    print('GPU_CLIENT_COUNT:',summary['gpu_client_count'],flush=True)
    print('GPU_CLIENT_OWNERS:',allowners,flush=True)
    print('GPU_FOOTPRINT_REASONS:',reasons,flush=True)
    print('DEDICATED_VRAM_PER_PID: UNVERIFIED',flush=True)

if __name__=='__main__': main()
