import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from owner_distribution import build, build_optional


class IsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.web = Path(self.tmp.name)
        (self.web / "region").mkdir()
        (self.web / "trades").mkdir()
        self.inv = self.web / "inventory.json"
        self.target = self.web / "owner-distributions.json"
        self.target.write_text('{"previous":true}')
        (self.web / "complexes.json").write_text(json.dumps({
            "generated":"2026-10-12", "complexes":[
                {"key":k,"code":"1","id":i} for i,k in enumerate(["good","bad"])]}))
        (self.web / "region/1.json").write_text(json.dumps({"c":{
            str(i):{"ty":{"27":[27.68,27.68,27.68,1]}} for i in range(2)}}))
        (self.web / "trades/1.json").write_text(json.dumps({
            "fields":["date","area","floor","amount","direct","cancelled","dong"],
            "complexes":{str(i):[["20260101",27.68,3,100000,0,0,"101"]] for i in range(2)}}))
        self.entries=[dict(complex_key=k,audit_only=False,expected_units=1,
            pools=[["101",3,27.68,1]],inventory_date="2026-10-12",
            publish_bands=["27"],area_verification={"counts":{"27":1}})
            for k in ["good","bad"]]

    def test_bad_complex_does_not_abort_good_complex(self):
        for kind in ("audit_only","total","band","unmatched"):
            entries=json.loads(json.dumps(self.entries))
            if kind=="audit_only": entries[1]["audit_only"]=True
            if kind=="total": entries[1]["expected_units"]=2
            if kind=="band": entries[1]["area_verification"]["counts"]["27"]=2
            if kind=="unmatched": entries[1]["pools"][0][0]="999"
            self.inv.write_text(json.dumps(entries))
            with self.assertLogs(level="ERROR"):
                out=build(self.web,self.inv)
            self.assertEqual(list(out["complexes"]),["good"])
            self.assertEqual(json.loads(self.target.read_text()),out)

    def test_global_failure_preserves_previous_and_returns(self):
        self.inv.write_text("{broken")
        with self.assertLogs(level="ERROR"):
            self.assertIsNone(build_optional(self.web,self.inv))
        self.assertEqual(self.target.read_text(),'{"previous":true}')

    def test_replace_failure_preserves_previous_and_cleans_temp(self):
        self.inv.write_text(json.dumps(self.entries))
        with patch("owner_distribution.os.replace",side_effect=OSError("disk error")):
            with self.assertLogs(level="ERROR"):
                self.assertIsNone(build_optional(self.web,self.inv))
        self.assertEqual(self.target.read_text(),'{"previous":true}')
        self.assertEqual(list(self.web.glob(".owner-*")),[])

    def test_rebuild_is_identical(self):
        self.inv.write_text(json.dumps(self.entries))
        build(self.web,self.inv)
        first=self.target.read_bytes()
        build(self.web,self.inv)
        self.assertEqual(first,self.target.read_bytes())
