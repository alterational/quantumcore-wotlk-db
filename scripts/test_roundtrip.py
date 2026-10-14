#!/usr/bin/env python3
"""Import OUR generated SQL into an empty isolated server, verify every row.
Not a general SQL parser; only accepts this exporter's statement layout.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
from export import identifier, json_value, encoded


def test(socket, root, report, host=None, port=3306, user="root"):
    """Use a disposable server only. MYSQL_TEST_PASSWORD is for CI/local tests."""
    import pymysql
    connection={'unix_socket':str(socket)} if socket else {'host':host,'port':port}
    conn=pymysql.connect(**connection,user=user,password=os.environ.get('MYSQL_TEST_PASSWORD',''),charset='utf8mb4',autocommit=True)
    catalog=json.loads((root/'catalog.json').read_text())
    with conn.cursor() as q:
        q.execute('SHOW DATABASES');existing={r[0] for r in q.fetchall()}
    targets={'legacy_mysql' if d['name']=='mysql' else d['name'] for d in catalog['databases']}
    if existing & targets:raise ValueError('Target server must be empty: '+str(existing & targets))
    count=0;statement=''
    with gzip.open(root/'quantumcore-mysql55.sql.gz','rt',encoding='utf-8') as dump, conn.cursor() as q:
        for line in dump:
            if not statement and (line.startswith('--') or not line.strip()):continue
            statement+=line
            if line.rstrip().endswith(';'):
                q.execute(statement);count+=1;statement=''
        assert not statement.strip()
    tables=[]
    for db in catalog['databases']:
        target='legacy_mysql' if db['name']=='mysql' else db['name']
        for t in db['tables']:
            name=t['name'];meta=json.loads((root/db['name']/name/'meta.json').read_text())
            full=f'{identifier(target)}.{identifier(name)}'
            with conn.cursor() as q:
                q.execute(f'CHECK TABLE {full} EXTENDED');check=q.fetchall()
                assert check[-1][2:]==('status','OK'),(full,check)
                q.execute(f'SELECT COUNT(*) FROM {full}');rows=q.fetchone()[0]
                assert rows==t['rows'],(full,rows,t['rows'])
                q.execute(f'SHOW FULL COLUMNS FROM {full}');columns=q.fetchall()
                assert [c[0] for c in columns]==[c['name'] for c in meta['columns']]
                assert [c[1] for c in columns]==[c['type'] for c in meta['columns']]
            expected=hashlib.sha256();actual=hashlib.sha256()
            for chunk in meta['chunks']:
                for row in json.loads((root/db['name']/name/chunk['file']).read_text()):expected.update(encoded(row)+b'\n')
            with conn.cursor(pymysql.cursors.SSCursor) as q:
                q.execute(f'SELECT * FROM {full}')
                for row in q:actual.update(encoded([json_value(v) for v in row])+b'\n')
            assert expected.digest()==actual.digest(), f'Row values differ: {full}'
            tables.append({'database':db['name'],'importedDatabase':target,'table':name,'rows':rows,'sha256':actual.hexdigest(),'valuesMatch':True,'schemaColumnsMatch':True,'check':'OK','sourceStatus':t['status']})
    result={'serverVersion':conn.get_server_info(),'statements':count,'rows':sum(t['rows'] for t in tables),'tables':tables}
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    conn.close();print(f'PASS: {count} statements, {len(tables)} tables, {result["rows"]} rows; every value matches')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--socket',type=Path);group.add_argument('--host')
    p.add_argument('--port',type=int,default=3306);p.add_argument('--user',default='root')
    p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--report',type=Path,default=Path('docs/roundtrip-checks.json'))
    a=p.parse_args();test(a.socket,a.data,a.report,a.host,a.port,a.user)
