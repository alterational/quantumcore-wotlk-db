#!/usr/bin/env python3
"""Extract only MyISAM tables to a new work directory and check offline.
Never start a server against the original archive. No automatic row repairs.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

SAFE_NAME = re.compile(r'^[A-Za-z0-9_]+$')


def extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    with zipfile.ZipFile(archive) as source:
        if sum(f.file_size for f in source.infolist()) > 4 * 1024**3:
            raise ValueError('Archive exceeds the 4 GiB extraction limit')
        seen = set()
        for info in source.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
                raise ValueError('Unsafe archive path: ' + info.filename)
            if len(path.parts) != 3 or path.parts[0] != 'data':
                continue  # Do not copy old PID, logs or InnoDB system files.
            _, db, filename = path.parts
            if not SAFE_NAME.fullmatch(db):
                raise ValueError('Unsafe database name')
            if path.suffix.lower() not in {'.frm', '.myd', '.myi'} and filename != 'db.opt':
                continue
            if not SAFE_NAME.fullmatch(path.stem):
                raise ValueError('Unsafe table name')
            if info.filename in seen:
                raise ValueError('Duplicate archive member')
            seen.add(info.filename)
            data = source.read(info)
            if path.suffix == '.frm' and (len(data) < 4 or data[:2] != b'\xfe\x01' or data[3] != 9):
                raise ValueError('Not a MyISAM FRM; use an engine-specific recovery: '+info.filename)
            target = destination / db / filename
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
            hashes[f'{db}/{filename}'] = hashlib.sha256(data).hexdigest()
    return hashes


def prepare(archive, work, checker):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=False)
    hashes = extract(archive, work / 'data')
    inventory = {'archiveSha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest(), 'files': hashes, 'tables': []}
    for frm in sorted((work / 'data').glob('*/*.frm')):
        missing = [ext for ext in ('MYD','MYI') if not frm.with_suffix('.'+ext).exists()]
        table = {'database': frm.parent.name, 'name': frm.stem, 'missing': missing}
        if not missing:
            check = subprocess.run([str(checker), '--check', '--read-only', str(frm.with_suffix(''))], capture_output=True, text=True)
            table['offlineCheckExit'] = check.returncode
            table['offlineCheck'] = check.stdout + check.stderr
        inventory['tables'].append(table)
    (work / 'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('work', type=Path, help='New directory, must not exist')
    parser.add_argument('--myisamchk', required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.archive, args.work, args.myisamchk)
    print(f"Prepared {len(report['tables'])} tables. Inventory: {args.work / 'inventory.json'}")
