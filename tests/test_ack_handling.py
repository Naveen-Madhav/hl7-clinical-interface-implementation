"""
Unit Tests for HL7 Acknowledgment (ACK) Generator
"""

import unittest
from engine.parser import parse_hl7_message
from engine.validator import ValidationResult, ValidationError
from engine.ack_handler import ACKHandler

class TestACKHandler(unittest.TestCase):
    def setUp(self):
        self.raw_adt = (
            "MSH|^~\\&|EPIC_EHR|HOSPITAL_A|RHAPSODY_IE|HOSPITAL_A|20260902093000||ADT^A01|MSG_ORIG_100|P|2.3\r"
            "PID|1||MRN12345^^^HOSPITAL^MR||DOE^JOHN||19850615|M\r"
        )
        self.msg = parse_hl7_message(self.raw_adt)

    def test_generate_positive_aa_ack(self):
        ack = ACKHandler.generate_ack(self.msg, ack_code="AA", text_message="Message accepted")

        self.assertEqual(ack.get_field("MSH-3"), "RHAPSODY_IE")
        self.assertEqual(ack.get_field("MSH-5"), "EPIC_EHR")
        self.assertEqual(ack.get_field("MSH-9"), "ACK")

        self.assertEqual(ack.get_field("MSA-1"), "AA")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ORIG_100")
        self.assertEqual(ack.get_field("MSA-3"), "Message accepted")

        self.assertFalse(ack.has_segment("ERR"))

    def test_generate_error_ae_ack_with_err_segment(self):
        val_res = ValidationResult(is_valid=False)
        val_res.errors.append(ValidationError(
            segment="PID", field_num=3, comp_num=1,
            error_code="101", severity="E",
            message="Required field missing: PID-3.1"
        ))

        ack = ACKHandler.generate_ack(
            self.msg, ack_code="AE",
            text_message="Validation error occurred",
            validation_result=val_res
        )

        self.assertEqual(ack.get_field("MSA-1"), "AE")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ORIG_100")
        self.assertTrue(ack.has_segment("ERR"))

        err = ack.get_segment("ERR")
        self.assertEqual(err.get_field_raw(1), "PID^3^1")
        self.assertIn("101", err.get_field_raw(3))
        self.assertEqual(err.get_field_raw(4), "E")

    def test_generate_reject_ar_ack(self):
        val_res = ValidationResult(is_valid=False)
        val_res.errors.append(ValidationError(
            segment="MSH", field_num=9, error_code="200", severity="F",
            message="Unsupported Message Type"
        ))

        ack = ACKHandler.generate_ack(
            self.msg, ack_code="AR",
            text_message="Message rejected",
            validation_result=val_res
        )

        self.assertEqual(ack.get_field("MSA-1"), "AR")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ORIG_100")
        self.assertEqual(ack.get_segment("ERR").get_field_raw(4), "F")

if __name__ == "__main__":
    unittest.main()
