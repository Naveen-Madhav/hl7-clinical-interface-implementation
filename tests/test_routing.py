"""
Unit Tests for Content-Based Routing Engine
"""

import unittest
from engine.parser import parse_hl7_message
from engine.router import HL7Router

class TestHL7Router(unittest.TestCase):
    def setUp(self):
        config = {
            "routing_rules": [
                {"match_criteria": {"message_code": "ADT"}, "destinations": ["CDR_CLINICAL"]},
                {"match_criteria": {"message_code": "ORM"}, "destinations": ["LIS_ORDERS"]},
                {"match_criteria": {"message_code": "ORU", "has_abnormal_flags": False}, "destinations": ["CDR_CLINICAL"]},
                {"match_criteria": {"message_code": "ORU", "has_abnormal_flags": True}, "destinations": ["CDR_CLINICAL", "STAT_ALERT_SERVICE"]}
            ]
        }
        self.router = HL7Router(config)

    def test_adt_routing_to_cdr(self):
        raw = "MSH|^~\\&|HOSPITAL_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_001|P|2.3\r"
        msg = parse_hl7_message(raw)
        dests = self.router.determine_destinations(msg)
        self.assertEqual(dests, ["CDR_CLINICAL"])

    def test_orm_routing_to_lis(self):
        raw = "MSH|^~\\&|HOSPITAL_CPOE|AMBULATORY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORM^O01|MSG_002|P|2.3\r"
        msg = parse_hl7_message(raw)
        dests = self.router.determine_destinations(msg)
        self.assertEqual(dests, ["LIS_ORDERS"])

    def test_oru_routine_routing_to_cdr(self):
        raw = "MSH|^~\\&|CERNER_LIS|PATHOLOGY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORU^R01|MSG_003|P|2.3\r"
        msg = parse_hl7_message(raw)
        msg.set_property("IsPanicResult", "false")
        dests = self.router.determine_destinations(msg)
        self.assertEqual(dests, ["CDR_CLINICAL"])

    def test_oru_critical_fork_to_stat_alert(self):
        raw = "MSH|^~\\&|CERNER_LIS|PATHOLOGY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORU^R01|MSG_004|P|2.3\r"
        msg = parse_hl7_message(raw)
        msg.set_property("IsPanicResult", "true")
        dests = self.router.determine_destinations(msg)
        self.assertIn("CDR_CLINICAL", dests)
        self.assertIn("STAT_ALERT_SERVICE", dests)

    def test_error_message_routes_to_dlq(self):
        raw = "MSH|^~\\&|HOSPITAL_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_005|P|2.3\r"
        msg = parse_hl7_message(raw)
        dests = self.router.determine_destinations(msg, is_error=True)
        self.assertEqual(dests, ["DLQ"])

if __name__ == "__main__":
    unittest.main()
