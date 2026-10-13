"""
Unit Tests for HL7 Transformation Engine
Tests workflow transformations for ADT, ORM, and ORU messages.
"""

import unittest
from engine.parser import parse_hl7_message
from engine.transformer import HL7Transformer

class TestHL7Transformer(unittest.TestCase):
    def setUp(self):
        self.transformer = HL7Transformer()

    def test_adt_name_and_sex_transformation(self):
        raw = (
            "MSH|^~\\&|HOSPITAL_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_001|P|2.3\r"
            "PID|1||MRN12345||smith^john^arthur||19850615|MALE\r"
        )
        msg = parse_hl7_message(raw)
        self.transformer.transform(msg)

        self.assertEqual(msg.get_field("PID-5.1"), "SMITH")
        self.assertEqual(msg.get_field("PID-5.2"), "JOHN")
        self.assertEqual(msg.get_field("PID-8"), "M")
        self.assertEqual(msg.get_field("PID-3.4"), "HOSPITAL_A")
        self.assertEqual(msg.get_field("PID-3.5"), "MR")

    def test_orm_loinc_mapping_and_order_sync(self):
        raw = (
            "MSH|^~\\&|HOSPITAL_CPOE|AMBULATORY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORM^O01|MSG_002|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19850615|M\r"
            "ORC|NW|ORD7788|||IP||^^^20260902120000^^S||20260902120000\r"
            "OBR|1|||CBC^Complete Blood Count^LOCAL|||20260902120000\r"
        )
        msg = parse_hl7_message(raw)
        self.transformer.transform(msg)

        self.assertEqual(msg.get_field("OBR-2.1"), "ORD7788")
        self.assertEqual(msg.get_field("OBR-4.1"), "58410-2")
        self.assertEqual(msg.get_field("OBR-4.3"), "LN")
        self.assertEqual(msg.get_property("OrderPriority"), "STAT")

    def test_oru_critical_value_detection(self):
        raw = (
            "MSH|^~\\&|CERNER_LIS|PATHOLOGY|RHAPSODY_IE|HOSPITAL_A|20260902093000||ORU^R01|MSG_003|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19850615|M\r"
            "OBR|1|ORD7788|FIL9900|2823-3^Potassium^LN\r"
            "OBX|1|NM|2823-3^Potassium^LN||6.9|mmol/L|3.5-5.0|HH|||F\r"
        )
        msg = parse_hl7_message(raw)
        self.transformer.transform(msg)

        self.assertEqual(msg.get_property("IsPanicResult"), "true")
        self.assertIn("6.9", msg.get_property("PanicFindings"))
        self.assertIn("HH", msg.get_property("PanicFindings"))

if __name__ == "__main__":
    unittest.main()
