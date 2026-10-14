#!/usr/bin/env python3
"""On a disposable copy only: upgrade indexes when CHECK TABLE requires it.
QUICK rebuilds indexes, never intentionally repairs data. Fail if any MYD changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from export import identifier


def upgrade(socket, work):
    import pymysql
    inventory=json.loads((work/'inventory.json').read_text())
    conn=pymysql.connect(unix_socket=str(socket),user='root',charset='utf8mb4',autocommit=True)
    log=[]
    for t in inventory['tables']:
        if t['missing']:continue
        db,n=t['database'],t['name'];full=f'{identifier(db)}.{identifier(n)}'
        p=work/'data'/db/(n+'.MYD')
        before=hashlib.sha256(p.read_bytes()).hexdigest()
        assert before==inventory['files'][f'{db}/{n}.MYD'], 'MYD differs from original'
        with conn.cursor() as q:
            q.execute(f'CHECK TABLE {full} EXTENDED');check=q.fetchall()
            if check and check[-1][2:]==('status','OK'):continue
            q.execute(f'REPAIR TABLE {full} QUICK');repair=q.fetchall()
            q.execute(f'CHECK TABLE {full} EXTENDED');after_check=q.fetchall()
            after=hashlib.sha256(p.read_bytes()).hexdigest()
            record={'database':db,'table':n,'beforeCheck':check,'repair':repair,'check':after_check,'mydBefore':before,'mydAfter':after,'mydUnchanged':before==after}
            log.append(record)
            (work/'index-upgrades.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n')
            assert before==after, 'QUICK changed MYD: stop and investigate'
            assert after_check and after_check[-1][2:]==('status','OK'), 'Repair unsuccessful'
    conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();upgrade(a.socket,a.work)
