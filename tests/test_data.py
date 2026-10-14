import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class DataTest(unittest.TestCase):
    def test_complete_export(self):
        spec=importlib.util.spec_from_file_location('validate',ROOT/'scripts/validate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.validate(ROOT/'data')
