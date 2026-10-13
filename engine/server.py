"""MLLP listener that delegates message handling to the processing service."""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Dict, List, Optional

from .mllp import send_mllp_message, unwrap_mllp
from .parser import HL7Message
from .pipeline import Dispatcher, HL7ProcessingService

logger = logging.getLogger(__name__)


class HL7InterfaceEngineServer:
    def __init__(
        self,
        config: Dict[str, Any],
        dlq_dir: Optional[str] = None,
        log_dir: Optional[str] = None,
        downstream_dispatcher: Optional[Dispatcher] = None,
    ) -> None:
        inbound = config.get("network", {}).get("inbound_listener", {})
        mllp = config.get("network", {}).get("mllp", {})
        self.host = inbound.get("host", "127.0.0.1")
        self.port = int(inbound.get("port", 2575))
        self.timeout = float(mllp.get("socket_timeout_seconds", 15))
        self.max_message_size = int(mllp.get("max_message_size_bytes", 1024 * 1024))
        self.max_connections = int(inbound.get("max_connections", 20))

        self.service = HL7ProcessingService(config, dlq_dir, log_dir, downstream_dispatcher)
        self.exception_mgr = self.service.exception_mgr
        self.dedup = self.service.dedup
        self.validator = self.service.validator
        self.transformer = self.service.transformer
        self.router = self.service.router

        self._server_sock: Optional[socket.socket] = None
        self._is_running = False
        self._threads: List[threading.Thread] = []
        self._semaphore = threading.BoundedSemaphore(self.max_connections)
        self.processed_count = 0
        self.error_count = 0

    def start(self) -> None:
        if self._is_running:
            return
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(self.max_connections)
        self._server_sock = server_sock
        self._is_running = True
        thread = threading.Thread(target=self._listen_loop, name="hl7-acceptor", daemon=True)
        thread.start()
        self._threads.append(thread)
        logger.info("HL7 MLLP listener started on %s:%d", self.host, self.port)

    def stop(self) -> None:
        self._is_running = False
        if self._server_sock is not None:
            self._server_sock.close()
            self._server_sock = None
        logger.info("HL7 MLLP listener stopped")

    def process_message(self, raw_message: str) -> HL7Message:
        self.processed_count += 1
        response = self.service.process_message(raw_message)
        if response.get_field("MSA-1") != "AA":
            self.error_count += 1
        return response

    def _listen_loop(self) -> None:
        while self._is_running and self._server_sock is not None:
            try:
                client, address = self._server_sock.accept()
            except OSError:
                if self._is_running:
                    logger.exception("Unable to accept an inbound MLLP connection")
                continue
            if not self._semaphore.acquire(blocking=False):
                logger.warning("Rejecting MLLP connection from %s: connection limit reached", address)
                client.close()
                continue
            thread = threading.Thread(
                target=self._handle_client,
                args=(client, address),
                name=f"hl7-client-{address[0]}:{address[1]}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def _handle_client(self, client: socket.socket, address: Any) -> None:
        buffer = bytearray()
        try:
            client.settimeout(self.timeout)
            while self._is_running:
                chunk = client.recv(4096)
                if not chunk:
                    return
                buffer.extend(chunk)
                if len(buffer) > self.max_message_size:
                    logger.warning("Closing oversized MLLP connection from %s", address)
                    return
                messages, remaining = unwrap_mllp(bytes(buffer))
                buffer = bytearray(remaining)
                for raw_message in messages:
                    send_mllp_message(client, self.process_message(raw_message).to_er7())
        except socket.timeout:
            logger.debug("MLLP connection from %s exceeded idle timeout", address)
        except (ConnectionError, OSError):
            logger.info("MLLP connection from %s closed during exchange", address)
        finally:
            client.close()
            self._semaphore.release()
