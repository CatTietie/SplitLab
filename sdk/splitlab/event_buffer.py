import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

import httpx

logger = logging.getLogger(__name__)


@dataclass
class EventRecord:
    id: str
    experiment_key: str
    group_name: str
    user_id: str
    event_name: str
    metadata: dict | None
    event_time: str

    def to_dict(self) -> dict:
        return {
            "experiment_key": self.experiment_key,
            "group_name": self.group_name,
            "user_id": self.user_id,
            "event_name": self.event_name,
            "metadata": self.metadata,
            "event_time": self.event_time,
        }


class EventBuffer:
    def __init__(
        self,
        api_url: str,
        flush_interval: float = 5.0,
        buffer_size: int = 100,
        persistence_path: str | None = None,
        api_key: str | None = None,
    ):
        self._api_url = api_url.rstrip("/")
        self._flush_interval = flush_interval
        self._buffer_size = buffer_size
        self._persistence_path = persistence_path
        self._api_key = api_key
        self._buffer: list[EventRecord] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._recover_persisted()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.flush()

    def track(self, experiment_key: str, group_name: str, user_id: str, event_name: str, metadata: dict | None = None):
        record = EventRecord(
            id=str(uuid.uuid4()),
            experiment_key=experiment_key,
            group_name=group_name,
            user_id=user_id,
            event_name=event_name,
            metadata=metadata,
            event_time=datetime.now(timezone.utc).isoformat(),
        )

        if self._persistence_path:
            self._append_to_wal(record)

        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self._buffer_size:
                self._do_flush()

    def flush(self):
        with self._lock:
            self._do_flush()

    def _flush_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(self._flush_interval)
            if self._stop_event.is_set():
                break
            with self._lock:
                self._do_flush()

    def _do_flush(self):
        if not self._buffer:
            return

        batch = self._buffer[:]
        payload = {"events": [e.to_dict() for e in batch]}

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{self._api_url}/api/v1/sdk/events",
                    json=payload,
                    headers=headers,
                )
            if resp.status_code in (200, 201, 202):
                self._buffer = []
                self._clear_wal()
                logger.debug(f"Flushed {len(batch)} events")
            else:
                logger.warning(f"Event flush failed: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Event flush error: {e}")

    def _append_to_wal(self, record: EventRecord):
        try:
            with open(self._persistence_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"WAL write error: {e}")

    def _clear_wal(self):
        if self._persistence_path and os.path.exists(self._persistence_path):
            try:
                os.remove(self._persistence_path)
            except Exception:
                pass

    def _recover_persisted(self):
        if not self._persistence_path or not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    record = EventRecord(
                        id=str(uuid.uuid4()),
                        experiment_key=data["experiment_key"],
                        group_name=data["group_name"],
                        user_id=data["user_id"],
                        event_name=data["event_name"],
                        metadata=data.get("metadata"),
                        event_time=data["event_time"],
                    )
                    self._buffer.append(record)
            logger.info(f"Recovered {len(self._buffer)} events from WAL")
        except Exception as e:
            logger.warning(f"WAL recovery error: {e}")
