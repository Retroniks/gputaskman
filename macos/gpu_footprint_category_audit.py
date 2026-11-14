"""Real machine audit: which graphics-related footprint categories exist for live GPU PIDs?"""
from __future__ import annotations
import csv, json, os, sys, tempfile, subprocess
from pathlib import Path

from gputaskman.collector import Collector
from gputaskman.report import to_dict
from gputaskman.macos import graphics_bytes
from gpu_pid_memory_probe import select_pids


def category_family(categories):
    if not isinstance(categories, dict):
        return 'unknown'
    tagged = [k for k,v in categories.items() if isinstance(k,str) and k.endswith('(graphics)')
              and isinstance(v,dict) and type(v.get('dirty')) in (int,float) and v['dirty']>=0]
    if tagged:
        return 'tagged_graphics'
    fallback = [k for k,v in categories.items() if isinstance(k,str)
                and ('ioaccelerator' in k.lower() or 'iosurface' in k.lower())
                and isinstance(v,dict) and type(v.get('dirty')) in (int,float) and v['dirty']>=0]
    return 'standalone_gpu_vm' if fallback else 'unavailable'


def footprint_details(pid):
    with tempfile.TemporaryDirectory(prefix='gtm033-') as td:
        dest=Path(td)/'footprint.json'
        try:
            result=subprocess.run(['/usr/bin/footprint','-f','bytes','-j',str(dest),'-p',str(pid)],
                                  capture_output=True,timeout=10)
            if not dest.exists():
                return {'status':f'no_json_exit_{result.returncode}', 'bytes':None, 'basis':'unavailable','categories':[]}
            info=json.loads(dest.read_text())
        except (OSError, subprocess.SubprocessError, ValueError):
            return {'status':'command_or_json_failed','bytes':None,'basis':'unavailable','categories':[]}
    procs=[p for p in info.get('processes') or [] if str(p.get('pid'))==str(pid)]
    if len(procs)!=1:
        return {'status':'no_unique_pid','bytes':None,'basis':'unavailable','categories':[]}
    categories=procs[0].get('categories') or {}
    if not isinstance(categories,dict):
        categories={}
    names=[name for name in categories if isinstance(name,str)
           and ('graphics' in name.lower() or 'ioaccelerator' in name.lower() or 'iosurface' in name.lower())]
    return {'status':'ok', 'bytes':graphics_bytes(procs[0]),
            'basis':category_family(categories), 'categories':sorted(names)}


def main():
    tsv=Path(sys.argv[1]); dest=Path(sys.argv[2]); cap=int(sys.argv[3]);
    collector=Collector(scan_budget=0.0)
    try:
        collector.sample()
        snap=to_dict(collector.sample())
    finally:
        collector.close()
    if (snap.get('adapter') or {}).get('vendor_id') != 0x1002:
        raise RuntimeError('RX580 AMD adapter not available')
    rows=snap.get('processes') or []
    pids=select_pids(rows,os.getuid(),max_count=cap)
    if not pids:
        raise RuntimeError('No accessible AMD GPU process to audit')
    records=[]
    for i,pid in enumerate(pids,1):
        found=next(p for p in rows if p['pid']==pid)
        val=footprint_details(pid)
        rec={'pid':pid,'name':found.get('name'),'gpu_pct':found.get('gpu_pct'),
             'status':val['status'],'category_source':val['basis'],
             'graphics_host_ram_bytes':val['bytes'], 'categories':';'.join(val['categories']),
             'dedicated_vram_bytes':None}
        records.append(rec)
        print(f'[PID LIVE] processed={i}/{len(pids)} pct={int(i*100/len(pids))} pid={pid} '
              f'graphics_host_ram={rec["graphics_host_ram_bytes"]} source={rec["category_source"]}',flush=True)
    columns=['pid','name','gpu_pct','status','category_source','graphics_host_ram_bytes',
             'categories','dedicated_vram_bytes']
    with tsv.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,delimiter='\t')
        writer.writeheader(); writer.writerows(records)
    summary={'device_vram_bytes':snap.get('vram_used'),
             'device_total_vram_bytes':snap.get('vram_total'),
             'total_gpu_client_rows':len(rows),'inspected':len(records),
             'graphics_known':sum(r['graphics_host_ram_bytes'] is not None for r in records),
             'graphics_positive':sum((r['graphics_host_ram_bytes'] or 0)>0 for r in records),
             'dedicated_per_pid_vram':'not verified', 'rows':records}
    dest.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('DEVICE_VRAM_BYTES:',summary['device_vram_bytes'])
    print('GPU_CLIENT_ROWS:',summary['total_gpu_client_rows'])
    print('GRAPHICS_FOOTPRINT_KNOWN:',summary['graphics_known'])
    print('GRAPHICS_FOOTPRINT_POSITIVE:',summary['graphics_positive'])
    print('DEDICATED_VRAM_PER_PID: NOT_VERIFIED')

if __name__=='__main__':
    main()
