"""
Comprehensive End-to-End Integration Test Suite
Tests complete Interface Engine pipeline for all 6 required portfolio competencies:
1. Missing identifiers (PID-3, ORC-2)
2. Invalid field values (DOB format, sex codes, order controls)
3. Unexpected message structures (missing segments, unknown types, unsupported versions)
4. Duplicate data detection (MSH-10 replay prevention)
5. Communication failures (downstream offline error handling)
6. Rejected acknowledgments (downstream AR/AE response handling)
"""

import unittest
import json
import os
import tempfile
from typing import Dict, Any, Tuple

from engine.server import HL7InterfaceEngineServer
from engine.parser import parse_hl7_message, HL7Message


class MockDownstreamHub:
    """Simulates LIS, CDR, and STAT downstream destinations in-memory."""
    def __init__(self):
        self.lis_messages = []
        self.cdr_messages = []
        self.stat_messages = []
        self.simulate_communication_failure = False
        self.simulate_rejection = False

    def reset(self):
        self.lis_messages.clear()
        self.cdr_messages.clear()
        self.stat_messages.clear()
        self.simulate_communication_failure = False
        self.simulate_rejection = False

    def dispatch(self, dest_info: Dict[str, Any], message: HL7Message) -> Tuple[bool, str]:
        if self.simulate_communication_failure:
            return False, "Connection error: [Errno 61] Connection refused (simulated offline port)"

        if self.simulate_rejection:
            return False, "Downstream returned AR (LIS Catalog Reject: Test code not recognized in Cerner Pathology Master)"

        sys_code = dest_info.get("system_code")
        if sys_code == "CERNER_LIS":
            self.lis_messages.append(message)
            return True, "AA"
        elif sys_code == "CLINICAL_CDR":
            self.cdr_messages.append(message)
            return True, "AA"
        elif sys_code == "STAT_ALERT":
            self.stat_messages.append(message)
            return True, "AA"
        return True, "AA"


class TestHL7IntegrationScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_path = "config/interface_config.json"
        with open(cls.config_path, "r", encoding="utf-8") as f:
            cls.config = json.load(f)

        cls.runtime_dir = tempfile.TemporaryDirectory(prefix="hl7-tests-")
        cls.config["deduplication"]["storage_file"] = os.path.join(cls.runtime_dir.name, "dedup.json")
        cls.test_dlq = os.path.join(cls.runtime_dir.name, "dlq")
        cls.test_logs = os.path.join(cls.runtime_dir.name, "logs")

        cls.mock_hub = MockDownstreamHub()
        cls.server = HL7InterfaceEngineServer(
            cls.config,
            dlq_dir=cls.test_dlq,
            log_dir=cls.test_logs,
            downstream_dispatcher=cls.mock_hub.dispatch
        )

    def setUp(self):
        self.mock_hub.reset()

    def test_01_nominal_adt_registration(self):
        """Valid ADT A01 message must be accepted (AA) and forwarded to CDR."""
        with open("sample_messages/nominal/ADT_A01_admit.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AA")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ADT_001")
        self.assertFalse(ack.has_segment("ERR"))

        self.assertTrue(any(m.get_field("MSH-10") == "MSG_ADT_001" for m in self.mock_hub.cdr_messages))

    def test_02_nominal_orm_lab_order(self):
        """Valid ORM O01 order must be transformed (LOINC mapped), accepted (AA), and routed to LIS."""
        with open("sample_messages/nominal/ORM_O01_new_order.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AA")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ORM_001")

        lis_msg = next((m for m in self.mock_hub.lis_messages if m.get_field("MSH-10") == "MSG_ORM_001"), None)
        self.assertIsNotNone(lis_msg)
        self.assertEqual(lis_msg.get_field("OBR-4.1"), "58410-2")

    def test_03_nominal_oru_routine_result(self):
        """Routine ORU R01 result must be delivered to CDR."""
        with open("sample_messages/nominal/ORU_R01_routine_result.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AA")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ORU_001")
        self.assertTrue(any(m.get_field("MSH-10") == "MSG_ORU_001" for m in self.mock_hub.cdr_messages))

    def test_04_nominal_oru_critical_result_fork(self):
        """Critical ORU R01 with HH/CRIT flags must fork to both CDR and STAT Alert Service."""
        with open("sample_messages/nominal/ORU_R01_critical_result.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AA")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ORU_002")

        self.assertTrue(any(m.get_field("MSH-10") == "MSG_ORU_002" for m in self.mock_hub.cdr_messages))
        self.assertTrue(any(m.get_field("MSH-10") == "MSG_ORU_002" for m in self.mock_hub.stat_messages))

    def test_05_error_missing_pid3_mrn(self):
        """Missing PID-3 MRN must generate AE ACK with ERR segment and route to DLQ."""
        with open("sample_messages/error_scenarios/ERR_missing_pid3_mrn.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AE")
        self.assertEqual(ack.get_field("MSA-2"), "ERR_MSG_002")
        self.assertTrue(ack.has_segment("ERR"))

        err = ack.get_segment("ERR")
        self.assertEqual(err.get_field_raw(1), "PID^3^1")
        self.assertIn("101", err.get_field_raw(3))

        dlq_records = self.server.exception_mgr.list_dlq_records()
        self.assertTrue(any(r.get("message_control_id") == "ERR_MSG_002" for r in dlq_records))

    def test_06_error_invalid_dob_format(self):
        """Invalid Date of Birth format in PID-7 must generate AE ACK with data type error (102)."""
        with open("sample_messages/error_scenarios/ERR_invalid_dob_format.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AE")
        self.assertEqual(ack.get_field("MSA-2"), "ERR_MSG_003")
        self.assertTrue(ack.has_segment("ERR"))

        err = ack.get_segment("ERR")
        self.assertIn("102", err.get_field_raw(3))

    def test_07_error_missing_mandatory_orc_segment(self):
        """ORM missing mandatory ORC segment must generate AE/AR ACK with sequence error (100)."""
        with open("sample_messages/error_scenarios/ERR_invalid_message_structure.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertIn(ack.get_field("MSA-1"), ("AE", "AR"))
        self.assertEqual(ack.get_field("MSA-2"), "ERR_MSG_004")
        self.assertTrue(ack.has_segment("ERR"))
        self.assertIn("ORC", ack.get_field("MSA-3"))

    def test_08_error_unknown_message_type(self):
        """Unknown message type (XYZ^Z99) must be rejected with AR and Table 0357 code 200."""
        with open("sample_messages/error_scenarios/ERR_unknown_message_type.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AR")
        self.assertEqual(ack.get_field("MSA-2"), "ERR_MSG_006")
        self.assertTrue(ack.has_segment("ERR"))
        err = ack.get_segment("ERR")
        self.assertIn("200", err.get_field_raw(3))

    def test_09_error_unsupported_hl7_version(self):
        """Unsupported version ID (e.g. 9.9) must be rejected with AR and error code 203."""
        with open("sample_messages/error_scenarios/ERR_unsupported_version.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AR")
        self.assertEqual(ack.get_field("MSA-2"), "ERR_MSG_007")
        self.assertTrue(ack.has_segment("ERR"))
        err = ack.get_segment("ERR")
        self.assertIn("203", err.get_field_raw(3))

    def test_10_error_duplicate_control_id(self):
        """Submitting an already processed Control ID (MSG_ADT_001) must be rejected with AR."""
        with open("sample_messages/error_scenarios/ERR_duplicate_control_id.hl7", "r") as f:
            raw = f.read()

        ack = self.server.process_message(raw)
        self.assertEqual(ack.get_field("MSA-1"), "AR")
        self.assertEqual(ack.get_field("MSA-2"), "MSG_ADT_001")
        self.assertIn("Duplicate", ack.get_field("MSA-3"))

    def test_11_error_downstream_communication_failure(self):
        """When downstream destination is unreachable, Interface Engine must return AE and write to DLQ."""
        self.mock_hub.simulate_communication_failure = True
        orm_test = (
            "MSH|^~\&|EPIC_CPOE|AMBULATORY|RHAPSODY_IE|HOSPITAL_A|20260902120000||ORM^O01|MSG_COMM_ERR_01|P|2.3\r"
            "PID|1||MRN100234^^^HOSPITAL_A^MR||DOE^JOHN||19850615|M\r"
            "PV1|1|I|ICU^01\r"
            "ORC|NW|ORD889999|||IP||^^^20260902120000^^R||20260902120000\r"
            "OBR|1|ORD889999||CBC^Complete Blood Count^LOCAL|||20260902120000\r"
        )
        ack = self.server.process_message(orm_test)
        self.assertEqual(ack.get_field("MSA-1"), "AE")
        self.assertIn("communication", ack.get_field("MSA-3").lower())

        dlq_records = self.server.exception_mgr.list_dlq_records()
        self.assertTrue(any(r.get("message_control_id") == "MSG_COMM_ERR_01" for r in dlq_records))

    def test_12_error_downstream_rejected_acknowledgment(self):
        """When downstream LIS rejects order with AR, engine must log error and return AE to caller."""
        self.mock_hub.simulate_rejection = True
        orm_test = (
            "MSH|^~\&|EPIC_CPOE|AMBULATORY|RHAPSODY_IE|HOSPITAL_A|20260902120000||ORM^O01|MSG_REJ_ACK_01|P|2.3\r"
            "PID|1||MRN100234^^^HOSPITAL_A^MR||DOE^JOHN||19850615|M\r"
            "PV1|1|I|ICU^01\r"
            "ORC|NW|ORD889988|||IP||^^^20260902120000^^R||20260902120000\r"
            "OBR|1|ORD889988||CBC^Complete Blood Count^LOCAL|||20260902120000\r"
        )
        ack = self.server.process_message(orm_test)
        self.assertEqual(ack.get_field("MSA-1"), "AE")
        self.assertIn("Downstream returned AR", ack.get_field("MSA-3"))

        dlq_records = self.server.exception_mgr.list_dlq_records()
        self.assertTrue(any(r.get("message_control_id") == "MSG_REJ_ACK_01" for r in dlq_records))

if __name__ == "__main__":
    unittest.main()
