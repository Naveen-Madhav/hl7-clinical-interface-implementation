"""Normalize and enrich the supported HL7 clinical workflows."""

from .parser import HL7Message

class HL7Transformer:
    SEX_MAP = {
        "MALE": "M", "M": "M", "1": "M",
        "FEMALE": "F", "F": "F", "2": "F",
        "OTHER": "O", "O": "O",
        "UNKNOWN": "U", "U": "U", "9": "U", "0": "U"
    }

    LOINC_MAP = {
        "CBC": ("58410-2", "Complete blood count with differential", "LN"),
        "BMP": ("24323-8", "Basic metabolic panel", "LN"),
        "CMP": ("24320-4", "Comprehensive metabolic panel", "LN"),
        "LIPID": ("57698-3", "Lipid panel with direct LDL", "LN"),
        "GLUCOSE": ("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "LN"),
        "POTASSIUM": ("2823-3", "Potassium [Moles/volume] in Serum or Plasma", "LN"),
        "TROPONIN": ("49563-0", "Troponin I.cardiac [Mass/volume] in Serum or Plasma", "LN")
    }

    CRITICAL_FLAGS = {"HH", "LL", "AA", "PANIC", "CRIT", "A!"}

    def transform(self, message: HL7Message) -> HL7Message:
        msg_code = message.get_field("MSH-9.1").upper()

        if msg_code == "ADT":
            self._transform_adt(message)
        elif msg_code == "ORM":
            self._transform_orm(message)
        elif msg_code == "ORU":
            self._transform_oru(message)

        return message

    def _transform_adt(self, msg: HL7Message) -> None:
        fam_name = msg.get_field("PID-5.1")
        giv_name = msg.get_field("PID-5.2")
        if fam_name:
            msg.set_field("PID-5.1", fam_name.strip().upper())
        if giv_name:
            msg.set_field("PID-5.2", giv_name.strip().upper())

        raw_sex = msg.get_field("PID-8")
        if raw_sex:
            cleaned = raw_sex.strip().upper()
            msg.set_field("PID-8", self.SEX_MAP.get(cleaned, "U"))
        else:
            msg.set_field("PID-8", "U")

        auth = msg.get_field("PID-3.4")
        if not auth or auth.strip() == "":
            msg.set_field("PID-3.4", "HOSPITAL_A")
        msg.set_field("PID-3.5", "MR")

        if msg.has_segment("PV1"):
            pclass = msg.get_field("PV1-2")
            if not pclass or pclass.strip() == "":
                msg.set_field("PV1-2", "O")

        mrn = msg.get_field("PID-3.1")
        msg.set_property("Tracking_PatientMRN", mrn)
        msg.set_property("Tracking_PatientName", f"{msg.get_field('PID-5.1')}^{msg.get_field('PID-5.2')}")
        msg.set_property("Transformed_Status", "SUCCESS")

    def _transform_orm(self, msg: HL7Message) -> None:
        orc_placer = msg.get_field("ORC-2.1") or msg.get_field("ORC-2")
        obr_placer = msg.get_field("OBR-2.1") or msg.get_field("OBR-2")

        if orc_placer and not obr_placer:
            msg.set_field("OBR-2.1", orc_placer)
        elif obr_placer and not orc_placer:
            msg.set_field("ORC-2.1", obr_placer)
            orc_placer = obr_placer

        test_code = msg.get_field("OBR-4.1")
        if test_code:
            upper_test = test_code.strip().upper()
            if upper_test in self.LOINC_MAP:
                loinc_code, loinc_text, system = self.LOINC_MAP[upper_test]
                msg.set_field("OBR-4.1", loinc_code)
                msg.set_field("OBR-4.2", loinc_text)
                msg.set_field("OBR-4.3", system)
                msg.set_property("LOINC_Mapped", "true")

        priority = "ROUTINE"
        raw_prio = msg.get_field("OBR-27.6") or msg.get_field("ORC-7.6")
        if raw_prio and raw_prio.strip().upper() in ("S", "STAT"):
            priority = "STAT"

        msg.set_property("OrderPriority", priority)
        msg.set_property("PlacerOrderNumber", orc_placer)
        msg.set_property("Transformed_Status", "SUCCESS")

    def _transform_oru(self, msg: HL7Message) -> None:
        obx_segments = msg.get_segments("OBX")
        is_panic = False
        panic_items = []

        for idx, obx in enumerate(obx_segments):
            abn_flag = obx.get_field_raw(8).strip().upper()
            test_id = obx.get_component(3, 1)
            test_name = obx.get_component(3, 2) or test_id
            obs_val = obx.get_field_raw(5)
            units = obx.get_component(6, 1)

            if abn_flag in self.CRITICAL_FLAGS:
                is_panic = True
                panic_items.append(f"{test_name}={obs_val} {units} [{abn_flag}]")

            status = obx.get_field_raw(11)
            if not status or status.strip() == "":
                obx.set_field_raw(11, "F")

        msg.set_property("IsPanicResult", "true" if is_panic else "false")
        if is_panic:
            msg.set_property("PanicFindings", "; ".join(panic_items))
        msg.set_property("Transformed_Status", "SUCCESS")
