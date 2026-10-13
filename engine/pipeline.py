"""Application service for processing one inbound HL7 message."""

from __future__ import annotations

import socket
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ack_handler import ACKHandler
from .deduplication import DeduplicationManager
from .exception_manager import ExceptionManager
from .mllp import receive_mllp_message, send_mllp_message
from .parser import HL7Message, parse_hl7_message
from .router import HL7Router
from .transformer import HL7Transformer
from .validator import HL7Validator, ValidationError, ValidationResult

Dispatcher = Callable[[Dict[str, Any], HL7Message], Tuple[bool, str]]


class HL7ProcessingService:
    def __init__(
        self,
        config: Dict[str, Any],
        dlq_dir: Optional[str] = None,
        log_dir: Optional[str] = None,
        downstream_dispatcher: Optional[Dispatcher] = None,
    ) -> None:
        network = config.get("network", {})
        inbound_config = network.get("inbound_listener", {})
        self.max_message_size = int(network.get("mllp", {}).get("max_message_size_bytes", 1024 * 1024))
        self.allowed_senders = set(inbound_config.get("allowed_senders", []))
        self.destinations = network.get("downstream_destinations", {})
        dedup_config = config.get("deduplication", {})
        exception_config = config.get("exception_management", {})

        self.validator = HL7Validator(
            strict_mode=config.get("validation_profiles", {}).get("strict_mode", True)
        )
        self.transformer = HL7Transformer()
        self.router = HL7Router(config)
        self.dedup = DeduplicationManager(
            storage_file=dedup_config.get("storage_file"),
            ttl_seconds=int(dedup_config.get("ttl_hours", 24) * 3600),
            max_size=int(dedup_config.get("cache_size", 10000)),
        )
        self.exception_mgr = ExceptionManager(
            dlq_dir=dlq_dir or exception_config.get("dlq_directory", "dlq"),
            log_dir=log_dir or exception_config.get("log_directory", "logs"),
        )
        self.downstream_dispatcher = downstream_dispatcher

    def process_message(self, raw_message: str) -> HL7Message:
        control_id = "UNKNOWN"
        message_type = "UNKNOWN"
        if not isinstance(raw_message, str):
            summary = "Unable to parse HL7 message: payload must be text"
            self._write_failure(str(raw_message), "PARSE_FAILURE", summary, control_id, message_type)
            return ACKHandler.generate_ack(None, "AR", summary, fallback_control_id=control_id)
        if len(raw_message.encode("utf-8")) > self.max_message_size:
            summary = f"HL7 message exceeds the {self.max_message_size}-byte limit"
            self._write_failure(raw_message, "MESSAGE_TOO_LARGE", summary, control_id, message_type)
            return ACKHandler.generate_ack(None, "AR", summary, fallback_control_id=control_id)
        try:
            message = parse_hl7_message(raw_message)
            control_id = message.get_field("MSH-10") or control_id
            message_type = message.get_field("MSH-9") or message_type
        except (TypeError, ValueError) as exc:
            summary = f"Unable to parse HL7 message: {exc}"
            self._write_failure(raw_message, "PARSE_FAILURE", summary, control_id, message_type)
            return ACKHandler.generate_ack(None, "AR", summary, fallback_control_id=control_id)

        sender = message.get_field("MSH-3.1") or message.get_field("MSH-3")
        if self.allowed_senders and sender not in self.allowed_senders:
            summary = f"Sender application '{sender or 'unknown'}' is not authorized"
            error = ValidationError("MSH", 3, 1, "200", "F", summary)
            result = ValidationResult(False, errors=[error])
            self._write_failure(raw_message, "AUTHORIZATION_FAILURE", summary, control_id, message_type)
            return ACKHandler.generate_ack(message, "AR", summary, validation_result=result)

        if self.dedup.is_duplicate(control_id):
            summary = f"Duplicate message rejected: control ID '{control_id}' has already been processed"
            error = ValidationError("MSH", 10, 0, "207", "F", summary)
            result = ValidationResult(False, errors=[error])
            self._write_failure(raw_message, "DUPLICATE_MESSAGE", summary, control_id, message_type)
            return ACKHandler.generate_ack(message, "AR", summary, validation_result=result)

        validation = self.validator.validate(message)
        if not validation.is_valid:
            summary = validation.get_summary_message()
            self._write_failure(
                raw_message,
                "VALIDATION_FAILURE",
                summary,
                control_id,
                message_type,
                {"errors": [error.__dict__ for error in validation.errors]},
            )
            return ACKHandler.generate_ack(
                message, validation.get_ack_code(), f"Validation failed: {summary}", validation
            )

        try:
            self.transformer.transform(message)
        except (TypeError, ValueError, KeyError) as exc:
            summary = f"Message transformation failed: {exc}"
            self._write_failure(raw_message, "TRANSFORMATION_FAILURE", summary, control_id, message_type)
            return ACKHandler.generate_ack(message, "AE", summary)

        destinations = self.router.determine_destinations(message)
        failures: List[str] = []
        for destination_key in destinations:
            if destination_key == "DLQ":
                continue
            destination = self.destinations.get(destination_key)
            if not destination:
                failures.append(f"Destination '{destination_key}' is not configured")
                continue
            delivered, detail = self._forward_to_downstream(destination, message)
            if not delivered:
                failures.append(f"{destination.get('name', destination_key)}: {detail}")

        if failures:
            summary = "; ".join(failures)
            self._write_failure(
                message.to_er7(), "DOWNSTREAM_DISPATCH_FAILURE", summary, control_id, message_type
            )
            return ACKHandler.generate_ack(
                message, "AE", f"Downstream communication failed: {summary}"
            )

        self.dedup.record(control_id)
        return ACKHandler.generate_ack(message, "AA", "Message accepted and delivered")

    def _write_failure(
        self,
        raw_message: str,
        category: str,
        summary: str,
        control_id: str,
        message_type: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.exception_mgr.route_to_dlq(
            raw_message=raw_message,
            error_category=category,
            error_summary=summary,
            control_id=control_id,
            message_type=message_type,
            details=details,
        )

    def _forward_to_downstream(self, destination: Dict[str, Any], message: HL7Message) -> Tuple[bool, str]:
        if self.downstream_dispatcher is not None:
            return self.downstream_dispatcher(destination, message)

        host = destination.get("host", "127.0.0.1")
        port = destination.get("port")
        timeout = float(destination.get("timeout_seconds", 5))
        if not isinstance(port, int) or not 1 <= port <= 65535:
            return False, "destination port is invalid"

        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                send_mllp_message(sock, message.to_er7())
                ack = parse_hl7_message(receive_mllp_message(sock, timeout))
            code = (ack.get_field("MSA-1") or "").upper()
            text = ack.get_field("MSA-3") or ""
            return (True, "AA") if code == "AA" else (False, f"Downstream returned {code} ({text})")
        except (OSError, ValueError, ConnectionError) as exc:
            return False, f"connection error: {exc}"
