import decimal
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
ex=load('export')
recover=load('recover')

class ExportTest(unittest.TestCase):
    def test_types(self):
        self.assertEqual(ex.json_value(2**64-1),'18446744073709551615')
        self.assertEqual(ex.json_value(decimal.Decimal('0.1000')),'0.1000')
        self.assertEqual(ex.json_value(b'\x00\xff'),{'$binary':'00ff'})
        self.assertIsNone(ex.json_value(None))
        with self.assertRaises(ValueError): ex.json_value(float('nan'))
    def test_chunks(self):
        rows=[('Я'*10,i) for i in range(1051)]
        batches=list(ex.chunks(rows,max_rows=500,max_bytes=1000))
        self.assertEqual(sum(map(len,batches)),1051)
        self.assertTrue(all(len(ex.encoded(b))<=1000 for b in batches))
        self.assertEqual(list(ex.chunks([])),[])
    def test_sql_literals(self):
        self.assertEqual(ex.sql_value(None),'NULL')
        self.assertEqual(ex.sql_value(b'\x00\xff'),"X'00ff'")
        self.assertEqual(ex.sql_value("O'Reilly\n\\"),"'O\\'Reilly\\n\\\\'")
        self.assertEqual(ex.identifier('a`b'),'`a``b`')
    def test_unsafe_archives(self):
        for name in ['../oops','/data/world/x.frm','data/../x.frm','data\\world\\x.frm']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)
                with zipfile.ZipFile(path/'bad.zip','w') as z:z.writestr(name,b'bad')
                with self.assertRaises(ValueError):recover.extract(path/'bad.zip',path/'out')
    def test_extract_allowlist_and_original_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with zipfile.ZipFile(p/'data.zip','w') as z:
                z.writestr('data/world/test.frm',b'\xfe\x01\x09\x09')
                z.writestr('data/world/test.MYD',b'original')
                z.writestr('data/server.pid','123')
                z.writestr('data/ibdata1','unused')
            before=(p/'data.zip').read_bytes()
            hashes=recover.extract(p/'data.zip',p/'out')
            self.assertEqual(len(hashes),2)
            self.assertEqual((p/'out/world/test.MYD').read_bytes(),b'original')
            self.assertFalse((p/'out/server.pid').exists())
            self.assertEqual(before,(p/'data.zip').read_bytes())
            with self.assertRaises(FileExistsError):recover.extract(p/'data.zip',p/'out')

if __name__=='__main__': unittest.main()
