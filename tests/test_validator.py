"""
Unit Tests for HL7 Validator Engine
Tests field validation, data types, required segments, and Table 0357 error codes.
"""

import unittest
from engine.parser import parse_hl7_message
from engine.validator import HL7Validator

class TestHL7Validator(unittest.TestCase):
    def setUp(self):
        self.validator = HL7Validator(strict_mode=True)

    def test_nominal_adt_validation(self):
        raw = (
            "MSH|^~\\&|EPIC_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_001|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19800101|M\r"
            "PV1|1|I|ICU^01\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.get_ack_code(), "AA")

    def test_missing_pid3_mrn(self):
        raw = (
            "MSH|^~\\&|EPIC_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_002|P|2.3\r"
            "PID|1||||DOE^JOHN||19800101|M\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.get_ack_code(), "AE")
        self.assertTrue(any(e.field_num == 3 and e.error_code == "101" for e in res.errors))

    def test_invalid_dob_format(self):
        raw = (
            "MSH|^~\\&|EPIC_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_003|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||1980-01-01|M\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.get_ack_code(), "AE")
        self.assertTrue(any(e.field_num == 7 and e.error_code == "102" for e in res.errors))

    def test_orm_missing_orc_segment(self):
        raw = (
            "MSH|^~\\&|EPIC_CPOE|AMBULATORY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORM^O01|MSG_004|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19800101|M\r"
            "OBR|1|ORD100||CBC^Complete Blood Count\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertFalse(res.is_valid)
        self.assertTrue(any(e.segment == "ORC" and e.error_code == "100" for e in res.errors))

    def test_oru_missing_obx_segment(self):
        raw = (
            "MSH|^~\\&|CERNER_LIS|PATHOLOGY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORU^R01|MSG_005|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19800101|M\r"
            "OBR|1|ORD100|FIL200|24323-8^BMP\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertFalse(res.is_valid)
        self.assertTrue(any(e.segment == "OBX" for e in res.errors))

    def test_unknown_message_type_rejection(self):
        raw = (
            "MSH|^~\\&|EPIC_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||XYZ^Z99|MSG_006|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19800101|M\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.get_ack_code(), "AR")
        self.assertTrue(any(e.error_code == "200" for e in res.errors))

    def test_unsupported_hl7_version_rejection(self):
        raw = (
            "MSH|^~\\&|EPIC_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_007|P|9.9\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19800101|M\r"
        )
        msg = parse_hl7_message(raw)
        res = self.validator.validate(msg)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.get_ack_code(), "AR")
        self.assertTrue(any(e.error_code == "203" for e in res.errors))

if __name__ == "__main__":
    unittest.main()
