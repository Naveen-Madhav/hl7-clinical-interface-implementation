"""Validate the message structures and code values this interface accepts."""

from dataclasses import dataclass, field
from typing import List, Optional, Set
import re
from .parser import HL7Message, HL7Segment

@dataclass
class ValidationError:
    segment: str
    field_num: int = 0
    comp_num: int = 0
    error_code: str = "101"
    severity: str = "E"
    message: str = ""

    def to_err_string(self) -> str:
        """
        Formats error into HL7 v2.5 ERR segment representation:
        ERR|<Segment>^<Seq>^<Field>^<Comp>||<ErrorCode>^<Message>^HL70357|<Severity>
        """
        loc = f"{self.segment}^{self.field_num}^{self.comp_num}" if self.segment else ""
        return f"ERR|{loc}||{self.error_code}^{self.message}^HL70357|{self.severity}"


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def get_highest_severity(self) -> str:
        if any(e.severity == "F" for e in self.errors):
            return "F"
        if any(e.severity == "E" for e in self.errors):
            return "E"
        if self.warnings:
            return "W"
        return "I"

    def get_ack_code(self) -> str:
        """
        Maps validation errors to HL7 Acknowledgment Codes:
        - AA: Application Accept
        - AE: Application Error (Validation / format / required field error)
        - AR: Application Reject (Structural failure, unknown message type, unsupported version)
        """
        if self.is_valid:
            return "AA"
        if any(e.severity == "F" or e.error_code in ("100", "200", "203") for e in self.errors):
            return "AR"
        return "AE"

    def get_summary_message(self) -> str:
        if self.is_valid:
            return "Message validated successfully"
        return "; ".join(e.message for e in self.errors)


class HL7Validator:
    SUPPORTED_VERSIONS: Set[str] = {"2.3", "2.3.1", "2.4", "2.5", "2.5.1"}
    SUPPORTED_MESSAGE_CODES: Set[str] = {"ADT", "ORM", "ORU"}
    VALID_SEX_CODES: Set[str] = {"M", "F", "O", "U", "A", "N", "MALE", "FEMALE", "OTHER", "UNKNOWN"}
    VALID_ORDER_CONTROLS: Set[str] = {"NW", "CA", "DC", "SC", "RE", "OK", "CR", "SN", "RO", "RU", "RP"}
    VALID_OBX_VALUE_TYPES: Set[str] = {"NM", "ST", "TX", "CE", "CWE", "SN", "IS", "ID", "DT", "TS"}

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def validate(self, message: HL7Message) -> ValidationResult:
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        if not message.segments:
            errors.append(ValidationError(
                segment="",
                error_code="100",
                severity="F",
                message="Structural Error: Empty message containing no segments"
            ))
            return ValidationResult(is_valid=False, errors=errors)

        first_seg = message.segments[0]
        if first_seg.name != "MSH":
            errors.append(ValidationError(
                segment=first_seg.name,
                error_code="100",
                severity="F",
                message=f"Segment Sequence Error: First segment must be MSH, found '{first_seg.name}'"
            ))
            return ValidationResult(is_valid=False, errors=errors)

        msg_code = message.get_field("MSH-9.1")
        trigger_event = message.get_field("MSH-9.2")
        if not msg_code:
            errors.append(ValidationError(
                segment="MSH", field_num=9, comp_num=1,
                error_code="101", severity="F",
                message="Missing required MSH-9.1 Message Code"
            ))
        elif msg_code not in self.SUPPORTED_MESSAGE_CODES:
            errors.append(ValidationError(
                segment="MSH", field_num=9, comp_num=1,
                error_code="200", severity="F",
                message=f"Unsupported Message Type: '{msg_code}' is not handled by this interface"
            ))

        control_id = message.get_field("MSH-10")
        if not control_id or control_id.strip() == "":
            errors.append(ValidationError(
                segment="MSH", field_num=10, comp_num=0,
                error_code="101", severity="F",
                message="Missing required MSH-10 Message Control ID"
            ))

        version_id = message.get_field("MSH-12")
        if not version_id:
            errors.append(ValidationError(
                segment="MSH", field_num=12, comp_num=0,
                error_code="101", severity="F",
                message="Missing required MSH-12 HL7 Version ID"
            ))
        elif version_id not in self.SUPPORTED_VERSIONS:
            errors.append(ValidationError(
                segment="MSH", field_num=12, comp_num=0,
                error_code="203", severity="F",
                message=f"Unsupported HL7 Version: '{version_id}'. Interface supports {sorted(self.SUPPORTED_VERSIONS)}"
            ))

        if any(e.severity == "F" for e in errors):
            return ValidationResult(is_valid=False, errors=errors)

        if msg_code == "ADT":
            self._validate_adt(message, errors, warnings)
        elif msg_code == "ORM":
            self._validate_orm(message, errors, warnings)
        elif msg_code == "ORU":
            self._validate_oru(message, errors, warnings)

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def _validate_adt(self, message: HL7Message, errors: List[ValidationError], warnings: List[ValidationError]) -> None:
        if not message.has_segment("PID"):
            errors.append(ValidationError(
                segment="PID", error_code="100", severity="E",
                message="Missing required PID (Patient Identification) segment in ADT message"
            ))
            return

        mrn = message.get_field("PID-3.1")
        if not mrn or mrn.strip() == "":
            errors.append(ValidationError(
                segment="PID", field_num=3, comp_num=1,
                error_code="101", severity="E",
                message="Missing required patient identifier (PID-3.1 Patient ID / MRN)"
            ))

        family_name = message.get_field("PID-5.1")
        given_name = message.get_field("PID-5.2")
        if not family_name:
            errors.append(ValidationError(
                segment="PID", field_num=5, comp_num=1,
                error_code="101", severity="E",
                message="Missing required patient family/last name in PID-5.1"
            ))
        if not given_name:
            errors.append(ValidationError(
                segment="PID", field_num=5, comp_num=2,
                error_code="101", severity="E",
                message="Missing required patient given/first name in PID-5.2"
            ))

        dob = message.get_field("PID-7")
        if not dob:
            errors.append(ValidationError(
                segment="PID", field_num=7, comp_num=0,
                error_code="101", severity="E",
                message="Missing required Date of Birth in PID-7"
            ))
        elif not self._is_valid_hl7_date(dob):
            errors.append(ValidationError(
                segment="PID", field_num=7, comp_num=0,
                error_code="102", severity="E",
                message=f"Data type error: Invalid Date of Birth format '{dob}' in PID-7. Expected YYYYMMDD."
            ))

        sex = message.get_field("PID-8")
        if not sex:
            warnings.append(ValidationError(
                segment="PID", field_num=8, comp_num=0,
                error_code="101", severity="W",
                message="Missing PID-8 Administrative Sex (will default to 'U')"
            ))
        elif sex.strip().upper() not in self.VALID_SEX_CODES:
            errors.append(ValidationError(
                segment="PID", field_num=8, comp_num=0,
                error_code="103", severity="E",
                message=f"Table value error: Invalid Administrative Sex '{sex}' in PID-8"
            ))

    def _validate_orm(self, message: HL7Message, errors: List[ValidationError], warnings: List[ValidationError]) -> None:
        if not message.has_segment("PID"):
            errors.append(ValidationError(
                segment="PID", error_code="100", severity="E",
                message="Missing required PID segment in ORM order message"
            ))
        if not message.has_segment("ORC"):
            errors.append(ValidationError(
                segment="ORC", error_code="100", severity="E",
                message="Missing required ORC (Common Order) segment in ORM order message"
            ))
        if not message.has_segment("OBR"):
            errors.append(ValidationError(
                segment="OBR", error_code="100", severity="E",
                message="Missing required OBR (Observation Request) segment in ORM order message"
            ))

        order_control = message.get_field("ORC-1")
        if not order_control:
            errors.append(ValidationError(
                segment="ORC", field_num=1, comp_num=0,
                error_code="101", severity="E",
                message="Missing required ORC-1 Order Control code"
            ))
        elif order_control.strip().upper() not in self.VALID_ORDER_CONTROLS:
            errors.append(ValidationError(
                segment="ORC", field_num=1, comp_num=0,
                error_code="103", severity="E",
                message=f"Table value error: Invalid Order Control code '{order_control}' in ORC-1"
            ))

        placer_order_orc = message.get_field("ORC-2.1") or message.get_field("ORC-2")
        if not placer_order_orc or placer_order_orc.strip() == "":
            errors.append(ValidationError(
                segment="ORC", field_num=2, comp_num=1,
                error_code="101", severity="E",
                message="Missing required ORC-2 Placer Order Number"
            ))

        service_id = message.get_field("OBR-4.1") or message.get_field("OBR-4")
        if not service_id or service_id.strip() == "":
            errors.append(ValidationError(
                segment="OBR", field_num=4, comp_num=1,
                error_code="101", severity="E",
                message="Missing required OBR-4 Universal Service Identifier (Order Test Code)"
            ))

    def _validate_oru(self, message: HL7Message, errors: List[ValidationError], warnings: List[ValidationError]) -> None:
        if not message.has_segment("PID"):
            errors.append(ValidationError(
                segment="PID", error_code="100", severity="E",
                message="Missing required PID segment in ORU observation result message"
            ))
        if not message.has_segment("OBR"):
            errors.append(ValidationError(
                segment="OBR", error_code="100", severity="E",
                message="Missing required OBR segment in ORU observation result message"
            ))

        obx_segments = message.get_segments("OBX")
        if not obx_segments:
            errors.append(ValidationError(
                segment="OBX", error_code="100", severity="E",
                message="Structural Error: ORU observation message contains zero OBX result segments"
            ))
            return

        for idx, obx in enumerate(obx_segments):
            val_type = obx.get_field_raw(2)
            if not val_type or val_type.strip().upper() not in self.VALID_OBX_VALUE_TYPES:
                errors.append(ValidationError(
                    segment="OBX", field_num=2, comp_num=0,
                    error_code="102", severity="E",
                    message=f"OBX({idx}): Invalid or missing Value Type '{val_type}' in OBX-2"
                ))

            obs_id = obx.get_field_raw(3)
            if not obs_id or obs_id.strip() == "":
                errors.append(ValidationError(
                    segment="OBX", field_num=3, comp_num=1,
                    error_code="101", severity="E",
                    message=f"OBX({idx}): Missing Observation Identifier in OBX-3"
                ))

            obs_val = obx.get_field_raw(5)
            if obs_val is None or obs_val == "":
                warnings.append(ValidationError(
                    segment="OBX", field_num=5, comp_num=0,
                    error_code="101", severity="W",
                    message=f"OBX({idx}): Observation Value in OBX-5 is blank"
                ))

            status = obx.get_field_raw(11)
            if not status or status.strip() == "":
                warnings.append(ValidationError(
                    segment="OBX", field_num=11, comp_num=0,
                    error_code="101", severity="W",
                    message=f"OBX({idx}): Missing Result Status in OBX-11"
                ))

    def _is_valid_hl7_date(self, val: str) -> bool:
        """
        Validates HL7 TS / DT formats: YYYYMMDD or YYYYMMDDHHMMSS[+/-ZZZZ]
        """
        val_clean = val.split("+")[0].split("-")[0].strip()
        return bool(re.match(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(\d{2,6})?$", val_clean))
