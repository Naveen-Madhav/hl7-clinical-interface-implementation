"""
Unit Tests for HL7 Message Deduplication Manager
"""

import unittest
import os
import time
from engine.deduplication import DeduplicationManager

class TestDeduplication(unittest.TestCase):
    def setUp(self):
        self.test_file = "logs/test_dedup.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.mgr = DeduplicationManager(storage_file=self.test_file, ttl_seconds=2)

    def tearDown(self):
        self.mgr.clear()
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_new_message_not_duplicate(self):
        self.assertFalse(self.mgr.is_duplicate("MSG_1001"))

    def test_record_and_detect_duplicate(self):
        self.mgr.record("MSG_1001")
        self.assertTrue(self.mgr.is_duplicate("MSG_1001"))
        self.assertFalse(self.mgr.is_duplicate("MSG_1002"))

    def test_ttl_expiration(self):
        self.mgr.record("MSG_EXPIRING")
        self.assertTrue(self.mgr.is_duplicate("MSG_EXPIRING"))
        time.sleep(2.1)
        self.assertFalse(self.mgr.is_duplicate("MSG_EXPIRING"))

    def test_disk_persistence(self):
        self.mgr.record("MSG_PERSIST")
        mgr2 = DeduplicationManager(storage_file=self.test_file, ttl_seconds=10)
        self.assertTrue(mgr2.is_duplicate("MSG_PERSIST"))

if __name__ == "__main__":
    unittest.main()
