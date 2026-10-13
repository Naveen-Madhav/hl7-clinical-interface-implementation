"""Build HL7 acknowledgments without exposing transport or parser internals."""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional
from .parser import HL7Message, HL7Segment
from .validator import ValidationResult

class ACKHandler:
    @staticmethod
    def generate_ack(
        original_message: Optional[HL7Message],
        ack_code: str = "AA",
        text_message: str = "Message processed successfully",
        validation_result: Optional[ValidationResult] = None,
        fallback_control_id: str = "UNKNOWN_ID"
    ) -> HL7Message:
        """
        Constructs an HL7 ACK response message.
        """
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%z")
        ack_control_id = f"ACK-{uuid4().hex}"

        if original_message and original_message.has_segment("MSH"):
            orig_msh = original_message.get_segment("MSH")
            orig_sending_app = orig_msh.get_component(3, 1) or "UNKNOWN_APP"
            orig_sending_fac = orig_msh.get_component(4, 1) or "UNKNOWN_FAC"
            orig_receiving_app = orig_msh.get_component(5, 1) or "RHAPSODY_IE"
            orig_receiving_fac = orig_msh.get_component(6, 1) or "HOSPITAL"
            orig_control_id = orig_msh.get_field_raw(10) or fallback_control_id
            orig_version = orig_msh.get_field_raw(12) or "2.3"
            orig_proc_id = orig_msh.get_field_raw(11) or "P"
            field_sep = orig_msh.field_sep or "|"
            encoding_chars = orig_msh.encoding_chars or "^~\\&"
        else:
            orig_sending_app = "UNKNOWN_APP"
            orig_sending_fac = "UNKNOWN_FAC"
            orig_receiving_app = "RHAPSODY_IE"
            orig_receiving_fac = "HOSPITAL"
            orig_control_id = fallback_control_id
            orig_version = "2.3"
            orig_proc_id = "P"
            field_sep = "|"
            encoding_chars = "^~\\&"

        msh_fields = [
            orig_receiving_app,
            orig_receiving_fac,
            orig_sending_app,
            orig_sending_fac,
            timestamp_str,
            "",
            "ACK",
            ack_control_id,
            orig_proc_id,
            orig_version,
        ]
        msh_seg = HL7Segment("MSH", msh_fields, field_sep=field_sep, encoding_chars=encoding_chars)

        msa_fields = [ack_code, orig_control_id, text_message]
        msa_seg = HL7Segment("MSA", msa_fields, field_sep=field_sep, encoding_chars=encoding_chars)

        segments = [msh_seg, msa_seg]

        if ack_code in ("AE", "AR"):
            if validation_result and validation_result.errors:
                first_err = validation_result.errors[0]
                loc = f"{first_err.segment}^{first_err.field_num}^{first_err.comp_num}" if first_err.segment else ""
                err_code = first_err.error_code
                severity = first_err.severity
                err_msg = first_err.message
            else:
                loc = ""
                err_code = "207"
                severity = "E"
                err_msg = text_message

            err_fields = [loc, "", f"{err_code}^{err_msg}^HL70357", severity]
            err_seg = HL7Segment("ERR", err_fields, field_sep=field_sep, encoding_chars=encoding_chars)
            segments.append(err_seg)

        return HL7Message(segments)
