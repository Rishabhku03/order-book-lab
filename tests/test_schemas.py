"""Ensure schema checks reject corrupted exports, including precision hazards."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import ROOT
from schemas import trace

class ExportSchema(unittest.TestCase):
    def test_valid_and_corrupted_trace(self):
        original=json.loads((ROOT/'web/data/lifecycle.json').read_text())
        trace(original)
        for key,value in [('order_id',9007199254740993),('timestamp_ns','18446744073709551616'),('type','BOGUS')]:
            changed=copy.deepcopy(original);changed['frames'][0]['event'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):trace(changed)
        changed=copy.deepcopy(original);changed['frames'][1]['analytics']['midpoint']=float('nan')
        with self.assertRaises(ValueError):trace(changed)
        changed=copy.deepcopy(original);changed['frames'][1]['event']['sequence']='0'
        with self.assertRaises(ValueError):trace(changed)
