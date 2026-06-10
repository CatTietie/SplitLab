import json
import logging
import threading
import time

import httpx

from splitlab.models import SDKConfig

logger = logging.getLogger(__name__)


class ConfigPoller:
    def __init__(self, api_url: str, poll_interval: float = 30.0, api_key: str | None = None):
        self._api_url = api_url.rstrip("/")
        self._poll_interval = poll_interval
        self._api_key = api_key
        self._config = SDKConfig()
        self._etag: str | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def config(self) -> SDKConfig:
        with self._lock:
            return self._config

    def start(self):
        self._fetch_config()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(self._poll_interval)
            if self._stop_event.is_set():
                break
            self._fetch_config()

    def _fetch_config(self):
        headers = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self._api_url}/api/v1/sdk/config", headers=headers)

            if resp.status_code == 304:
                return

            if resp.status_code == 200:
                data = resp.json()
                new_config = SDKConfig.from_dict(data)
                etag = resp.headers.get("ETag", "").strip('"')
                with self._lock:
                    self._config = new_config
                    self._etag = etag
            else:
                logger.warning(f"Config fetch failed: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Config fetch error: {e}")
