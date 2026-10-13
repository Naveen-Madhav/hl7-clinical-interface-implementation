"""Resolve validated messages to configured downstream destinations."""

from typing import Any, Dict, List

from .parser import HL7Message


class HL7Router:
    DEFAULT_DESTINATIONS = {
        "ADT": ["CDR_CLINICAL"],
        "ORM": ["LIS_ORDERS"],
        "ORU": ["CDR_CLINICAL"],
    }

    def __init__(self, config: Dict[str, Any]) -> None:
        self.routing_rules = config.get("routing_rules", [])

    def determine_destinations(self, message: HL7Message, is_error: bool = False) -> List[str]:
        if is_error:
            return ["DLQ"]

        message_code = message.get_field("MSH-9.1").upper()
        trigger_event = message.get_field("MSH-9.2").upper()
        has_abnormal_flags = message.get_property("IsPanicResult", "false").lower() == "true"

        for rule in self.routing_rules:
            criteria = rule.get("match_criteria", {})
            if criteria.get("message_code", "").upper() != message_code:
                continue
            events = {event.upper() for event in criteria.get("trigger_events", [])}
            if trigger_event not in events:
                continue
            if "has_abnormal_flags" in criteria and criteria["has_abnormal_flags"] != has_abnormal_flags:
                continue
            return list(rule.get("destinations", []))
        if message_code == "ORU" and has_abnormal_flags:
            return ["CDR_CLINICAL", "STAT_ALERT_SERVICE"]
        return list(self.DEFAULT_DESTINATIONS.get(message_code, ["DLQ"]))
