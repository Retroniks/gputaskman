"""Audit GPU memory fields linked to IORegistry GPU client creators.
This audits field names and values; a per-client property is NOT assumed to be VRAM
or exclusive ownership unless its driver semantics are established separately.
"""
from __future__ import annotations
import plistlib
import re
import subprocess
from collections import Counter

CREATOR = re.compile(r'\bpid\s+(\d+)\b', re.I)
KEY = re.compile(r'vram|(?:^|[^a-z])memory|allocated|resident|footprint|(?:^|[^a-z])bytes|heap|buffer',re.I)

def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():
            if isinstance(v,(dict,list,tuple)):
                yield from walk(v)
    elif isinstance(value,(tuple,list)):
        for v in value:
            if isinstance(v,(dict,list,tuple)):
                yield from walk(v)

def summarize(nodes):
    """Return bounded aggregate counts, never invent process ownership."""
    hits=Counter()
    pid_hits=Counter()
    creators=set()
    for node in walk(nodes):
        creator=node.get('IOUserClientCreator','')
        match=CREATOR.search(creator) if isinstance(creator,str) else None
        if not match:
            continue
        pid=int(match.group(1))
        creators.add(pid)
        for name,value in node.items():
            if name=='IOUserClientCreator' or (not KEY.search(str(name)) and name != 'PerformanceStatistics'):
                continue
            if type(value) in (int,float):
                hits[(str(name), 'number')]+=1
                pid_hits[(pid,str(name))]+=1
            elif isinstance(value,dict):
                for inner,number in value.items():
                    if KEY.search(str(inner)) and type(number) in (int,float):
                        hits[(str(name)+'.'+str(inner),'number')]+=1
                        pid_hits[(pid,str(name)+'.'+str(inner))]+=1
    return creators,hits,pid_hits

def query():
    proc=subprocess.run(['/usr/sbin/ioreg','-a','-l','-w','0','-c','IOAccelerator'],
                        capture_output=True,timeout=20,check=True)
    return plistlib.loads(proc.stdout)

def export_tsv(nodes,dest):
    pids, fields, owners = summarize(nodes)
    with open(dest,'w',encoding='utf-8') as f:
        f.write('scope\tfield\tcount\tnote\n')
        for (field,kind),n in sorted(fields.items()):
            f.write(f'client-field\t{field}\t{n}\tsemantics-unverified\n')
        f.write(f'summary\tclient_pids\t{len(pids)}\tPID-is-client-creator-not-proven-exclusive-VRAM-owner\n')
        f.write(f'summary\tclient_pid_memory_fields\t{len(owners)}\tfield-count-only\n')
    return {'creator_pids':len(pids),'numeric_memory_fields':sum(fields.values()),
            'distinct_field_names':len(fields),'pid_field_pairs':len(owners)}
