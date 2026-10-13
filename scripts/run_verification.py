#!/usr/bin/env python3
"""Run the representative HL7 transactions through the local engine."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.parser import HL7Message, parse_hl7_message
from engine.server import HL7InterfaceEngineServer


class RecordingDispatcher:
    def __init__(self) -> None:
        self.messages: dict[str, list[HL7Message]] = {}

    def dispatch(self, destination: dict, message: HL7Message) -> tuple[bool, str]:
        self.messages.setdefault(destination.get("system_code", "unknown"), []).append(message)
        return True, "AA"


def load_config(project_root: Path, state_dir: Path) -> dict:
    with (project_root / "config" / "interface_config.json").open(encoding="utf-8") as file:
        config = json.load(file)
    config["deduplication"]["storage_file"] = str(state_dir / "dedup.json")
    return config


def run() -> int:
    project_root = Path(__file__).resolve().parents[1]
    transaction_paths = sorted((project_root / "sample_messages" / "nominal").glob("*.hl7"))
    with tempfile.TemporaryDirectory(prefix="hl7-verification-") as state:
        dispatcher = RecordingDispatcher()
        server = HL7InterfaceEngineServer(
            load_config(project_root, Path(state)),
            dlq_dir=str(Path(state) / "dlq"),
            log_dir=str(Path(state) / "logs"),
            downstream_dispatcher=dispatcher.dispatch,
        )
        failures = []
        for path in transaction_paths:
            raw_message = path.read_text(encoding="utf-8")
            message = parse_hl7_message(raw_message)
            ack = server.process_message(raw_message)
            if ack.get_field("MSA-1") != "AA":
                failures.append(f"{path.name}: {ack.get_field('MSA-3')}")
            else:
                print(f"{path.name}: accepted ({message.get_field('MSH-10')})")
        print(f"Accepted {len(transaction_paths) - len(failures)}/{len(transaction_paths)} messages")
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
