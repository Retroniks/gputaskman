#!/usr/bin/env python3
"""Read-only Intel AMD IORegistry probe, independent of the Apple Silicon backend."""
import json, plistlib, subprocess, time, sys
from collections import defaultdict

def query(*args):
    p = subprocess.run(['/usr/sbin/ioreg','-a','-l','-w','0',*args], capture_output=True, timeout=12)
    if p.returncode or not p.stdout:
        return {'error': f'ioreg exit={p.returncode}', 'entries': []}
    try:
        return {'entries': plistlib.loads(p.stdout)}
    except (plistlib.InvalidFileException, ValueError) as e:
        return {'error': type(e).__name__, 'entries': []}

def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, (tuple, list)):
        for x in obj:
            yield from walk(x)

def parse(raw):
    nodes=list(walk(raw['entries']))
    perf=[n['PerformanceStatistics'] for n in nodes if isinstance(n.get('PerformanceStatistics'),dict)]
    clients=defaultdict(dict)
    for n in nodes:
        creator=n.get('IOUserClientCreator')
        if not isinstance(creator,str) or not creator.startswith('pid '): continue
        pid_token=creator.split(',',1)[0].split()
        if len(pid_token)!=2 or not pid_token[1].isdigit(): continue
        pid=pid_token[1]
        key=str(n.get('IORegistryEntryID', id(n)))
        usage=n.get('AppUsage')
        if isinstance(usage,list):
            times=[v.get('accumulatedGPUTime') for v in usage if isinstance(v,dict)]
            times=[x for x in times if isinstance(x,(int,float))]
            if times: clients[pid][key]=sum(times)
    return {'node_count':len(nodes), 'performance_statistics':perf[:3],
            'per_process_gpu_ns':dict(clients),
            'creator_count':sum(1 for n in nodes if 'IOUserClientCreator' in n),
            'client_count_with_gpu_time':sum(map(len,clients.values()))}

def main():
    samples=[]
    for i in range(2):
        r=query('-c','IOAccelerator')
        sample=parse(r)
        sample['time_monotonic_ns']=time.monotonic_ns()
        if 'error' in r:sample['error']=r['error']
        samples.append(sample)
        if i==0: time.sleep(1.5)
    a,b=samples
    elapsed=(b['time_monotonic_ns']-a['time_monotonic_ns'])/1e9
    percentages={}
    for pid, clients in b['per_process_gpu_ns'].items():
        old=a['per_process_gpu_ns'].get(pid,{})
        overlap=set(clients)&set(old)
        if overlap:
            delta=sum(max(0,clients[k]-old[k]) for k in overlap)
            percentages[pid]=round(100*delta/(elapsed*1e9),2)
    output={'schema':1,'kind':'macos-intel-amd-readonly-probe',
            'elapsed_seconds':round(elapsed,3),'samples':samples,
            'process_gpu_pct_from_persistent_clients':percentages,
            'note':'Process GPU percentages are preliminary; counts are sampled only for clients with matching stable IDs.'}
    print(json.dumps(output,indent=2,default=str))
    if not any(s['performance_statistics'] for s in samples): return 2
    return 0
if __name__=='__main__':sys.exit(main())
