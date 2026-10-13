#!/usr/bin/env python3
"""
Mock Cerner LIS (Laboratory Information System) Inbound MLLP Listener
Simulates port 2576 receiving ORM orders.
Can be configured to simulate normal AA acknowledgments or rejection (AE/AR) scenarios.
"""

import socket
import threading
import sys
import os
import argparse
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engine.mllp import send_mllp_message, receive_mllp_message, unwrap_mllp
from engine.parser import parse_hl7_message
from engine.ack_handler import ACKHandler

class MockLISServer:
    def __init__(self, host="127.0.0.1", port=2576, simulate_rejection=False, simulate_drop=False):
        self.host = host
        self.port = port
        self.simulate_rejection = simulate_rejection
        self.simulate_drop = simulate_drop
        self.is_running = False
        self.received_messages = []
        self._server_sock = None
        self._thread = None

    def start(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(5)
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[*] Mock Cerner LIS listening on {self.host}:{self.port}")

    def stop(self):
        self.is_running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass

    def _run(self):
        while self.is_running:
            try:
                client_sock, addr = self._server_sock.accept()
                raw_payload = receive_mllp_message(client_sock, timeout=5.0)
                if not raw_payload:
                    client_sock.close()
                    continue

                msg = parse_hl7_message(raw_payload)
                ctrl_id = msg.get_field("MSH-10")
                order_num = msg.get_field("ORC-2.1") or msg.get_field("OBR-2.1")
                test_code = msg.get_field("OBR-4.1")
                print(f"[LIS] Received ORM Order {order_num} (Test: {test_code}, ControlID: {ctrl_id})")
                self.received_messages.append(msg)

                if self.simulate_drop:
                    print(f"[LIS] Simulating communication failure: dropping socket without ACK")
                    client_sock.close()
                    continue

                if self.simulate_rejection:
                    print(f"[LIS] Simulating Application Rejection (AR) for order {order_num}")
                    ack = ACKHandler.generate_ack(
                        original_message=msg,
                        ack_code="AR",
                        text_message="LIS Catalog Reject: Test code not recognized in Cerner Pathology Master"
                    )
                else:
                    ack = ACKHandler.generate_ack(
                        original_message=msg,
                        ack_code="AA",
                        text_message="LIS Accepted order into laboratory worklist"
                    )

                send_mllp_message(client_sock, ack.to_er7())
                client_sock.close()

            except Exception:
                if not self.is_running:
                    break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Mock Cerner LIS")
    parser.add_argument("--port", type=int, default=2576, help="Port to listen on")
    parser.add_argument("--reject", action="store_true", help="Simulate AR rejection")
    parser.add_argument("--drop", action="store_true", help="Simulate connection drop")
    args = parser.parse_args()

    server = MockLISServer(port=args.port, simulate_rejection=args.reject, simulate_drop=args.drop)
    server.start()
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        server.stop()
        print("\nMock LIS stopped.")
