"""Persist failed HL7 transactions with enough context for replay analysis."""

import os
import json
from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ExceptionManager:
    def __init__(self, dlq_dir: str = "dlq", log_dir: str = "logs"):
        self.dlq_dir = dlq_dir
        self.log_dir = log_dir
        os.makedirs(self.dlq_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

    def route_to_dlq(
        self,
        raw_message: str,
        error_category: str,
        error_summary: str,
        control_id: str = "UNKNOWN",
        message_type: str = "UNKNOWN",
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Saves the failed message into the Dead-Letter Queue with an audit descriptor.
        Returns the created DLQ file path.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        safe_cid = "".join(c for c in control_id if c.isalnum() or c in ("-", "_")) or "NOCONTROLID"
        filename = f"DLQ_{error_category}_{safe_cid}_{timestamp}.json"
        filepath = os.path.join(self.dlq_dir, filename)

        payload = {
            "dlq_record_id": filename.replace(".json", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_control_id": control_id,
            "message_type": message_type,
            "error_category": error_category,
            "error_summary": error_summary,
            "diagnostic_details": details or {},
            "raw_message_er7": raw_message
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.warning("Message [%s] routed to DLQ file: %s (%s: %s)", control_id, filepath, error_category, error_summary)
        except OSError as ex:
            logger.error("Failed to write DLQ file for message [%s]: %s", control_id, ex)

        return filepath

    def list_dlq_records(self) -> list:
        records = []
        if not os.path.exists(self.dlq_dir):
            return records
        for f in sorted(os.listdir(self.dlq_dir)):
            if f.endswith(".json"):
                path = os.path.join(self.dlq_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as jf:
                        records.append(json.load(jf))
                except (OSError, ValueError):
                    logger.warning("Skipping unreadable DLQ record: %s", path)
        return records
