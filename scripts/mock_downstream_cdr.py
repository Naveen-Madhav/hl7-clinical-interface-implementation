#!/usr/bin/env python3
"""
Mock Clinical Data Repository (CDR) & STAT Alert Service Inbound MLLP Listeners
- CDR listens on port 2577 (ADT demographics & ORU results)
- STAT Alert Service listens on port 2578 (Critical/Panic lab results)
"""

import socket
import threading
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engine.mllp import send_mllp_message, receive_mllp_message
from engine.parser import parse_hl7_message
from engine.ack_handler import ACKHandler

class MockCDRServer:
    def __init__(self, cdr_port=2577, stat_port=2578):
        self.cdr_port = cdr_port
        self.stat_port = stat_port
        self.is_running = False
        self.cdr_messages = []
        self.stat_messages = []
        self._cdr_sock = None
        self._stat_sock = None

    def start(self):
        self.is_running = True
        self._cdr_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._cdr_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._cdr_sock.bind(("127.0.0.1", self.cdr_port))
        self._cdr_sock.listen(5)
        threading.Thread(target=self._run_cdr, daemon=True).start()
        print(f"[*] Mock Clinical Data Repository (CDR) listening on 127.0.0.1:{self.cdr_port}")

        self._stat_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._stat_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._stat_sock.bind(("127.0.0.1", self.stat_port))
        self._stat_sock.listen(5)
        threading.Thread(target=self._run_stat, daemon=True).start()
        print(f"[*] Mock STAT Critical Alert Service listening on 127.0.0.1:{self.stat_port}")

    def stop(self):
        self.is_running = False
        for s in (self._cdr_sock, self._stat_sock):
            if s:
                try:
                    s.close()
                except Exception:
                    pass

    def _run_cdr(self):
        while self.is_running:
            try:
                sock, _ = self._cdr_sock.accept()
                raw = receive_mllp_message(sock, timeout=5.0)
                if not raw:
                    sock.close()
                    continue
                msg = parse_hl7_message(raw)
                msg_type = msg.get_field("MSH-9")
                ctrl_id = msg.get_field("MSH-10")
                patient_name = msg.get_field("PID-5.1") + ", " + msg.get_field("PID-5.2")
                mrn = msg.get_field("PID-3.1")
                print(f"[CDR] Stored {msg_type} for Patient {patient_name} (MRN: {mrn}, ControlID: {ctrl_id})")
                self.cdr_messages.append(msg)

                ack = ACKHandler.generate_ack(msg, ack_code="AA", text_message="CDR Successfully committed record")
                send_mllp_message(sock, ack.to_er7())
                sock.close()
            except Exception:
                if not self.is_running:
                    break

    def _run_stat(self):
        while self.is_running:
            try:
                sock, _ = self._stat_sock.accept()
                raw = receive_mllp_message(sock, timeout=5.0)
                if not raw:
                    sock.close()
                    continue
                msg = parse_hl7_message(raw)
                ctrl_id = msg.get_field("MSH-10")
                mrn = msg.get_field("PID-3.1")
                print(f"[STAT_ALERT] !!! PANIC LAB RESULT RECEIVED for MRN: {mrn} (ControlID: {ctrl_id}) !!! Triggering pager alert.")
                self.stat_messages.append(msg)

                ack = ACKHandler.generate_ack(msg, ack_code="AA", text_message="STAT Alert dispatched to on-call physician")
                send_mllp_message(sock, ack.to_er7())
                sock.close()
            except Exception:
                if not self.is_running:
                    break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Mock CDR & STAT Alert Services")
    parser.add_argument("--cdr-port", type=int, default=2577)
    parser.add_argument("--stat-port", type=int, default=2578)
    args = parser.parse_args()

    server = MockCDRServer(cdr_port=args.cdr_port, stat_port=args.stat_port)
    server.start()
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        server.stop()
        print("\nMock CDR & STAT servers stopped.")
