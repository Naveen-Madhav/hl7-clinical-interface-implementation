#!/usr/bin/env python3
"""
Interactive Command-Line HL7 MLLP Client
Transmits HL7 v2 messages framed in MLLP to any target host and port.
Displays returning ACK response and decodes MSA and ERR fields.
"""

import socket
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engine.mllp import send_mllp_message, receive_mllp_message
from engine.parser import parse_hl7_message

def send_message_file(filepath: str, host: str = "127.0.0.1", port: int = 2575, timeout: float = 10.0):
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        return False, None

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return send_raw_hl7(content, host=host, port=port, timeout=timeout)

def send_raw_hl7(content: str, host: str = "127.0.0.1", port: int = 2575, timeout: float = 10.0):
    print(f"\n=======================================================")
    print(f"Connecting to MLLP Endpoint {host}:{port} (Timeout: {timeout}s)")
    print(f"=======================================================")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((host, port))

        print("\n--- OUTBOUND HL7 MESSAGE ---")
        for line in content.strip().splitlines():
            if line.strip():
                print(f"  {line.strip()}")

        send_mllp_message(sock, content)

        raw_ack = receive_mllp_message(sock, timeout=timeout)
        print("\n--- INBOUND ACK RESPONSE ---")
        for line in raw_ack.strip().splitlines():
            if line.strip():
                print(f"  {line.strip()}")

        ack_msg = parse_hl7_message(raw_ack)
        ack_code = ack_msg.get_field("MSA-1")
        orig_ctrl = ack_msg.get_field("MSA-2")
        ack_text = ack_msg.get_field("MSA-3")

        print(f"\n[ACK ANALYSIS]")
        print(f"  Status Code:             {ack_code} ({'ACCEPT' if ack_code == 'AA' else 'ERROR/REJECT'})")
        print(f"  Original Message ID:     {orig_ctrl}")
        print(f"  Acknowledgment Text:     {ack_text}")

        if ack_msg.has_segment("ERR"):
            err_seg = ack_msg.get_segment("ERR")
            print(f"  Error Location:          {err_seg.get_field_raw(1)}")
            print(f"  Error Code & Text:       {err_seg.get_field_raw(3)}")
            print(f"  Error Severity:          {err_seg.get_field_raw(4)}")

        return True, ack_msg

    except socket.timeout:
        print(f"[ERROR] Connection timed out waiting for ACK from {host}:{port}")
        return False, None
    except ConnectionRefusedError:
        print(f"[ERROR] Connection refused by {host}:{port}. Is the interface engine running?")
        return False, None
    except Exception as ex:
        print(f"[ERROR] Transport failure: {ex}")
        return False, None
    finally:
        try:
            sock.close()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transmit HL7 file over MLLP")
    parser.add_argument("file", help="Path to .hl7 file to transmit")
    parser.add_argument("--host", default="127.0.0.1", help="Target MLLP host")
    parser.add_argument("--port", type=int, default=2575, help="Target MLLP port")
    parser.add_argument("--timeout", type=float, default=10.0, help="Socket timeout")
    args = parser.parse_args()

    send_message_file(args.file, host=args.host, port=args.port, timeout=args.timeout)
