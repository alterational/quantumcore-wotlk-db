#!/usr/bin/env python3
"""Rebuild schema-only scratch tables from FRM. NEVER treat them as recovered data.
Run only on the isolated recovery server and its working copy.
"""
import argparse
import json
from pathlib import Path
import shutil
from export import identifier


def recover(socket, work):
    import pymysql
    inventory=json.loads((work/'inventory.json').read_text())
    conn=pymysql.connect(unix_socket=str(socket),user='root',charset='utf8mb4',autocommit=True)
    log=[]
    for table in inventory['tables']:
        if not table['missing']:continue
        db,name=table['database'],table['name']
        target='recovery_schema_'+db
        with conn.cursor() as cur:cur.execute(f'CREATE DATABASE IF NOT EXISTS {identifier(target)}')
        dest=work/'data'/target
        if (dest/(name+'.frm')).exists():raise FileExistsError('Scratch table already exists')
        shutil.copy2(work/'data'/db/(name+'.frm'),dest/(name+'.frm'))
        (dest/(name+'.MYD')).touch(exist_ok=False)
        with conn.cursor() as cur:
            cur.execute(f'REPAIR TABLE {identifier(target)}.{identifier(name)} USE_FRM')
            result=cur.fetchall()
            if not result or result[-1][2:]!=('status','OK'):raise RuntimeError(result)
        table['schemaDatabase']=target
        log.append({'database':db,'table':name,'result':result,'note':'Empty scratch MYD, schema extraction only. Source rows remain missing.'})
    (work/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
    (work/'schema-recovery.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n')
    conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();recover(a.socket,a.work)
