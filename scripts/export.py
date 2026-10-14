#!/usr/bin/env python3
"""Export a checked legacy MySQL Unix socket to bounded static JSON and SQL.
All source table names come from the recovery inventory, never browser input.
"""
import argparse
import datetime
import decimal
import gzip
import hashlib
import json
import math
import re
from pathlib import Path


def identifier(value):
    return '`' + value.replace('`', '``') + '`'


def json_value(value):
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return {'$binary': value.hex()}
    if isinstance(value, (int, float, decimal.Decimal, datetime.date, datetime.timedelta)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite database number')
        # Strings keep BIGINT/DECIMAL exact in JavaScript.
        return str(value)
    raise TypeError(type(value))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value) + b'\n')


def chunks(rows, max_rows=500, max_bytes=128 * 1024):
    batch, size = [], 2
    for row in rows:
        data = [json_value(v) for v in row]
        length = len(encoded(data)) + 1
        if batch and (len(batch) >= max_rows or size + length > max_bytes):
            yield batch
            batch, size = [], 2
        batch.append(data)
        size += length
    if batch:
        yield batch


def sql_value(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, (int, float, decimal.Decimal)):
        return str(value)
    value = str(value).replace('\\', '\\\\').replace("'", "\\'").replace('\x00','\\0').replace('\n','\\n').replace('\r','\\r').replace('\x1a','\\Z')
    return "'" + value + "'"


def export(socket, inventory_path, output, report_path):
    import pymysql
    inventory = json.loads(inventory_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    conn = pymysql.connect(unix_socket=str(socket), user='root', charset='utf8mb4', autocommit=True)
    catalog = {'format': 1, 'archiveSha256':inventory['archiveSha256'], 'serverVersion':conn.get_server_info(), 'tables':0,'rows':0,'incomplete':0,'databases':[]}
    dbs, reports = {}, []
    dump_path=output/'quantumcore-mysql55.sql.gz'
    with gzip.open(dump_path,'wt',encoding='utf-8',newline='\n') as dump:
        dump.write('-- Recovered Denwer archive. INCOMPLETE: missing source rows are not invented.\n-- mysql is renamed legacy_mysql. Never import old privilege tables into mysql.\nSET NAMES utf8mb4;\nSET @OLD_SQL_MODE=@@SQL_MODE;\nSET SQL_MODE=\'NO_AUTO_VALUE_ON_ZERO\';\nSET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS;\nSET FOREIGN_KEY_CHECKS=0;\n')
        for source in inventory['tables']:
            db, name = source['database'], source['name']
            if db not in dbs:
                dbs[db]={'name':db,'rows':0,'tables':[]}
                target_db='legacy_mysql' if db=='mysql' else db
                dump.write(f'CREATE DATABASE IF NOT EXISTS {identifier(target_db)};\nUSE {identifier(target_db)};\n')
            full=f'{identifier(db)}.{identifier(name)}'
            schema_full=f'{identifier(source.get("schemaDatabase",db))}.{identifier(name)}'
            dest=output/db/name
            meta={'name':name,'database':db,'engine':'MyISAM','columns':[],'chunks':[],'ddl':None,'rows':0,'status':'ok','warning':None,'missing':source['missing']}
            report={**source}
            if 'offlineCheck' in report:
                report['offlineCheck']=report['offlineCheck'].replace(str(inventory_path.parent/'data')+'/', 'data/')
            try:
                with conn.cursor() as cur:
                    cur.execute(f'SHOW CREATE TABLE {schema_full}')
                    meta['ddl']=cur.fetchone()[1]
                    cur.execute(f'SHOW FULL COLUMNS FROM {schema_full}')
                    meta['columns']=[{'name':c[0],'type':c[1],'collation':c[2],'nullable':c[3]=='YES','key':c[4],'default':json_value(c[5]),'extra':c[6],'comment':c[8]} for c in cur.fetchall()]
                    if source['missing']:
                        meta['status']='missing-files'
                        meta['warning']='В исходном ZIP отсутствуют '+', '.join('.'+x for x in source['missing'])+'. Структура восстановлена из .frm; строки не восстановлены и не считаются пустой таблицей.'
                    else:
                        cur.execute(f'CHECK TABLE {full} EXTENDED')
                        checks=cur.fetchall()
                        report['serverCheck']=checks
                        if not checks or checks[-1][2:] != ('status','OK'):
                            raise ValueError('CHECK TABLE EXTENDED did not return OK: '+str(checks))
                        cur.execute(f'SELECT COUNT(*) FROM {full}')
                        expected=cur.fetchone()[0]
                if meta['status']=='ok':
                    with conn.cursor(pymysql.cursors.SSCursor) as stream:
                        stream.execute(f'SELECT * FROM {full}')
                        for i,batch in enumerate(chunks(stream)):
                            filename=f'{i:05d}.json'
                            write_json(dest/filename,batch)
                            meta['chunks'].append({'file':filename,'start':meta['rows'],'rows':len(batch),'bytes':(dest/filename).stat().st_size,'sha256':hashlib.sha256((dest/filename).read_bytes()).hexdigest()})
                            meta['rows']+=len(batch)
                    if expected!=meta['rows']:
                        raise ValueError(f'COUNT mismatch: {expected} != {meta["rows"]}')
                    match=re.search(r'Data records:\s*(\d+)',source.get('offlineCheck',''))
                    if not match or int(match[1])!=expected:
                        raise ValueError('Original offline MyISAM count does not match exported rows')
                    relative=f'{db}/{name}.MYD'
                    digest=hashlib.sha256((inventory_path.parent/'data'/relative).read_bytes()).hexdigest()
                    if digest!=inventory['files'][relative]:
                        raise ValueError('Source MYD has changed since extraction')
                    report.update(sourceMydSha256=digest,sourceMydUnchanged=True,offlineRecordsVerified=int(match[1]))
                    report['countVerified']=expected
                if meta['ddl']:
                    if meta['status']!='ok': dump.write(f'-- WARNING {db}.{name}: MISSING SOURCE DATA; schema only.\n')
                    dump.write(meta['ddl']+';\n')
                    if meta['status']=='ok' and meta['rows']:
                        with conn.cursor(pymysql.cursors.SSCursor) as stream:
                            stream.execute(f'SELECT * FROM {full}')
                            for row in stream:
                                dump.write(f'INSERT INTO {identifier(name)} VALUES ('+','.join(sql_value(v) for v in row)+');\n')
            except Exception as error:
                # Fail closed: never label a partial export as a valid catalog/dump.
                raise RuntimeError(f'Export failed for {db}.{name}: {error}') from error
            write_json(dest/'meta.json',meta)
            brief={k:meta[k] for k in ('name','rows','status','engine')}
            dbs[db]['tables'].append(brief)
            dbs[db]['rows']+=meta['rows']
            catalog['tables']+=1
            catalog['rows']+=meta['rows']
            catalog['incomplete']+=meta['status']!='ok'
            report.update(status=meta['status'],rows=meta['rows'],warning=meta['warning'])
            reports.append(report)
            print(f'{db}.{name}: {meta["status"]}, {meta["rows"]} rows',flush=True)
        dump.write('SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;\nSET SQL_MODE=@OLD_SQL_MODE;\n')
    order={'world':0,'characters':1,'realmd':2,'mysql':3}
    catalog['databases']=sorted(dbs.values(),key=lambda db:(order.get(db['name'],4),db['name']))
    write_json(output/'catalog.json',catalog)
    write_json(report_path,{'archiveSha256':inventory['archiveSha256'],'serverVersion':catalog['serverVersion'],'tables':reports})
    conn.close()
    return catalog


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket',type=Path,required=True)
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('data'))
    p.add_argument('--report',type=Path,default=Path('docs/recovery-checks.json'))
    a=p.parse_args()
    c=export(a.socket,a.inventory,a.output,a.report)
    print({k:v for k,v in c.items() if k!='databases'})
