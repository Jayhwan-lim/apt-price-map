import unittest
from datetime import datetime
from unittest.mock import patch
from building_facts import supply_due, KST

class SupplyQueueRegressionTest(unittest.TestCase):
    def test_missing_record_is_new_work(self):
        self.assertTrue(supply_due(None, [[84,85]], 12))
        self.assertTrue(supply_due({}, [[84,85]], 12))

    def test_no_area_type_does_not_schedule(self):
        self.assertFalse(supply_due(None, [], 12))

    def test_fresh_unreadable_or_complete_stays_skipped(self):
        today=datetime.now(KST).strftime("%Y%m%d")
        self.assertFalse(supply_due({"f":today,"pg":6,"a":{}}, [[84,85]], 12))
        self.assertFalse(supply_due({"f":today,"done":True}, [[84,85]], 12))

    def test_old_unreadable_record_can_be_refreshed(self):
        self.assertTrue(supply_due({"f":"20000101","pg":6,"a":{}}, [[84,85]], 12))

    def test_fresh_partial_record_resumes(self):
        today=datetime.now(KST).strftime("%Y%m%d")
        with patch("building_facts.covered",return_value=False):
            self.assertTrue(supply_due({"f":today,"pg":2,"a":{"x":1}}, [[84,85]], 12))
            self.assertFalse(supply_due({"f":today,"pg":12,"a":{"x":1}}, [[84,85]], 12))
