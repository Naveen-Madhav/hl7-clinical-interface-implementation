"""Thread-safe, time-bounded tracking for HL7 message control IDs."""

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DeduplicationManager:
    def __init__(self, storage_file: Optional[str] = None, ttl_seconds: int = 86400, max_size: int = 10000):
        self.storage_file = storage_file
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.lock = threading.RLock()
        self.cache: Dict[str, float] = {}

        if self.storage_file and os.path.exists(self.storage_file):
            self._load_from_disk()

    def is_duplicate(self, control_id: str) -> bool:
        """
        Checks if the control_id has been seen within the TTL window.
        """
        if not control_id:
            return False

        with self.lock:
            self._prune_expired()
            return control_id in self.cache

    def record(self, control_id: str) -> None:
        """
        Records a newly observed control_id with current epoch timestamp.
        """
        if not control_id:
            return

        with self.lock:
            self.cache[control_id] = time.time()
            if len(self.cache) > self.max_size:
                oldest_id = min(self.cache, key=self.cache.get)
                del self.cache[oldest_id]

            if self.storage_file:
                self._save_to_disk()

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()
            if self.storage_file and os.path.exists(self.storage_file):
                try:
                    os.remove(self.storage_file)
                except OSError:
                    pass

    def _prune_expired(self) -> None:
        now = time.time()
        expired = [cid for cid, ts in self.cache.items() if (now - ts) > self.ttl_seconds]
        for cid in expired:
            del self.cache[cid]

    def _load_from_disk(self) -> None:
        try:
            with open(self.storage_file, "r", encoding="utf-8") as file:
                data = json.load(file)
            now = time.time()
            self.cache = {
                str(control_id): float(timestamp)
                for control_id, timestamp in data.items()
                if now - float(timestamp) <= self.ttl_seconds
            }
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Unable to load deduplication state from %s: %s", self.storage_file, exc)
            self.cache = {}

    def _save_to_disk(self) -> None:
        if not self.storage_file:
            return
        path = Path(self.storage_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(self.cache, file, separators=(",", ":"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            logger.error("Unable to persist deduplication state to %s: %s", path, exc)
