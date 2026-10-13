"""MLLP framing and socket helpers for HL7 v2 messages."""

import socket
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger("HL7_MLLP")

class MLLPProtocol:
    START_BLOCK = b'\x0b'
    END_BLOCK = b'\x1c'
    CARRIAGE_RETURN = b'\x0d'
    TRAILER = b'\x1c\x0d'


def wrap_mllp(payload: str, encoding: str = "utf-8") -> bytes:
    """
    Wraps an HL7 ER7 string in MLLP envelope bytes: <VT> + payload + <FS><CR>.
    """
    if isinstance(payload, str):
        payload_bytes = payload.encode(encoding, errors="replace")
    else:
        payload_bytes = bytes(payload)
    return MLLPProtocol.START_BLOCK + payload_bytes + MLLPProtocol.TRAILER


def unwrap_mllp(buffer: bytes, encoding: str = "utf-8") -> Tuple[List[str], bytes]:
    """
    Extracts all complete MLLP frames from a raw bytes buffer.
    Returns:
        (extracted_messages, remaining_buffer)
    """
    messages = []
    ptr = 0
    buf_len = len(buffer)
    
    while ptr < buf_len:
        start_idx = buffer.find(MLLPProtocol.START_BLOCK, ptr)
        if start_idx == -1:
            return messages, b""
        
        end_idx = buffer.find(MLLPProtocol.TRAILER, start_idx + 1)
        if end_idx == -1:
            return messages, buffer[start_idx:]
        
        raw_msg = buffer[start_idx + 1 : end_idx]
        try:
            decoded_msg = raw_msg.decode(encoding, errors="replace")
            messages.append(decoded_msg)
        except Exception as ex:
            logger.error("Failed to decode MLLP frame: %s", ex)
        
        ptr = end_idx + 2
        
    return messages, b""


def send_mllp_message(sock: socket.socket, message: str, encoding: str = "utf-8") -> None:
    """
    Transmits an MLLP wrapped message over an open TCP socket.
    """
    framed = wrap_mllp(message, encoding)
    sock.sendall(framed)


def receive_mllp_message(sock: socket.socket, timeout: float = 10.0, encoding: str = "utf-8") -> str:
    """
    Reads from a TCP socket until a complete MLLP frame is received or timeout expires.
    """
    sock.settimeout(timeout)
    buffer = bytearray()
    
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            if buffer:
                raise ConnectionError("Socket closed prematurely while waiting for MLLP frame")
            raise ConnectionResetError("Connection closed by peer")
        
        buffer.extend(chunk)
        
        start_idx = buffer.find(MLLPProtocol.START_BLOCK)
        if start_idx != -1:
            end_idx = buffer.find(MLLPProtocol.TRAILER, start_idx + 1)
            if end_idx != -1:
                raw_payload = buffer[start_idx + 1 : end_idx]
                return raw_payload.decode(encoding, errors="replace")
