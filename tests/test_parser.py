"""
Unit Tests for HL7 Parser & Serializer
"""

import unittest
from engine.parser import parse_hl7_message, HL7Message, HL7Segment

class TestHL7Parser(unittest.TestCase):
    def setUp(self):
        self.raw_adt = (
            "MSH|^~\\&|HOSPITAL_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_001|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN^M||19800101|M|||100 MAIN ST^^NEW YORK^NY^10001\r"
            "PV1|1|I|ICU^01^01\r"
        )

    def test_parse_msh_fields(self):
        msg = parse_hl7_message(self.raw_adt)
        self.assertEqual(msg.get_field("MSH-1"), "|")
        self.assertEqual(msg.get_field("MSH-2"), "^~\\&")
        self.assertEqual(msg.get_field("MSH-3"), "HOSPITAL_EHR")
        self.assertEqual(msg.get_field("MSH-4"), "HOSPITAL_A")
        self.assertEqual(msg.get_field("MSH-9"), "ADT^A01")
        self.assertEqual(msg.get_field("MSH-9.1"), "ADT")
        self.assertEqual(msg.get_field("MSH-9.2"), "A01")
        self.assertEqual(msg.get_field("MSH-10"), "MSG_001")
        self.assertEqual(msg.get_field("MSH-12"), "2.3")

    def test_parse_pid_components(self):
        msg = parse_hl7_message(self.raw_adt)
        self.assertEqual(msg.get_field("PID-3.1"), "MRN12345")
        self.assertEqual(msg.get_field("PID-3.4"), "HOSPITAL")
        self.assertEqual(msg.get_field("PID-5.1"), "DOE")
        self.assertEqual(msg.get_field("PID-5.2"), "JOHN")
        self.assertEqual(msg.get_field("PID-5.3"), "M")
        self.assertEqual(msg.get_field("PID-7"), "19800101")
        self.assertEqual(msg.get_field("PID-8"), "M")

    def test_set_and_serialize_fields(self):
        msg = parse_hl7_message(self.raw_adt)
        msg.set_field("PID-5.1", "SMITH")
        msg.set_field("PID-8", "F")
        self.assertEqual(msg.get_field("PID-5.1"), "SMITH")
        self.assertEqual(msg.get_field("PID-8"), "F")

        serialized = msg.to_er7()
        self.assertIn("PID|1||MRN12345^^^HOSPITAL^MR||SMITH^JOHN^M", serialized)
        self.assertIn("|F|", serialized)

    def test_empty_string_rejection(self):
        with self.assertRaises(ValueError):
            parse_hl7_message("")

if __name__ == "__main__":
    unittest.main()
