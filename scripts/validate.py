#!/usr/bin/env python3
"""Verify ALL exported chunk hashes, widths, counts, schemas and size budgets."""
import hashlib
import json
from pathlib import Path
import re


def validate(root=Path('data')):
    catalog=json.loads((root/'catalog.json').read_text())
    files={root/'catalog.json',root/'quantumcore-mysql55.sql.gz'}
    total=table_count=incomplete=0
    max_chunk=0
    for db in catalog['databases']:
        db_rows=0
        assert re.fullmatch(r'[a-zA-Z0-9_]+',db['name'])
        for table in db['tables']:
            table_count+=1
            assert re.fullmatch(r'[a-zA-Z0-9_]+',table['name'])
            path=root/db['name']/table['name']
            meta_path=path/'meta.json'
            files.add(meta_path)
            meta=json.loads(meta_path.read_text())
            assert meta['name']==table['name'] and meta['database']==db['name']
            assert meta['ddl'] and meta['columns'], f'Missing schema: {path}'
            assert meta['status']==table['status'] and meta['rows']==table['rows']
            count=0
            for c in meta['chunks']:
                assert c['start']==count
                assert re.fullmatch(r'\d{5}\.json',c['file'])
                f=path/c['file'];files.add(f)
                raw=f.read_bytes()
                assert len(raw)==c['bytes']
                assert hashlib.sha256(raw).hexdigest()==c['sha256']
                rows=json.loads(raw)
                assert len(rows)==c['rows'] and 0<len(rows)<=500
                assert all(len(row)==len(meta['columns']) for row in rows)
                assert all(v is None or isinstance(v,str) or (isinstance(v,dict) and set(v)=={'$binary'}) for row in rows for v in row)
                assert len(raw)<=128*1024+1 or len(rows)==1
                count+=len(rows);max_chunk=max(max_chunk,len(raw))
            assert count==table['rows']
            if table['status']!='ok':
                incomplete+=1
                assert count==0 and meta['warning']
            db_rows+=count
        assert db_rows==db['rows']
        total+=db_rows
    assert total==catalog['rows'] and table_count==catalog['tables'] and incomplete==catalog['incomplete']
    actual={f for f in root.rglob('*') if f.is_file()}
    assert actual==files, f'Unexpected or missing files: {actual ^ files}'
    assert (root/'catalog.json').stat().st_size<100*1024
    print(f'PASS: {table_count} tables, {total:,} rows, {incomplete} incomplete, {len(files)} files; largest chunk {max_chunk:,} bytes')

if __name__=='__main__':validate()
