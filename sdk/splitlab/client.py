import logging
import threading

import httpx

from splitlab.config_poller import ConfigPoller
from splitlab.event_buffer import EventBuffer
from splitlab.splitter import get_variant
from splitlab.targeting import evaluate_targeting

logger = logging.getLogger(__name__)


class SplitLabClient:
    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        poll_interval: float = 30.0,
        flush_interval: float = 5.0,
        buffer_size: int = 100,
        persistence_path: str | None = None,
    ):
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._poller = ConfigPoller(api_url, poll_interval=poll_interval, api_key=api_key)
        self._buffer = EventBuffer(
            api_url,
            flush_interval=flush_interval,
            buffer_size=buffer_size,
            persistence_path=persistence_path,
            api_key=api_key,
        )
        self._user_attributes: dict[str, dict[str, str]] = {}
        self._attr_buffer: list[dict] = []
        self._attr_lock = threading.Lock()
        self._poller.start()
        self._buffer.start()

    def set_user_attributes(self, user_id: str, attributes: dict[str, str]) -> None:
        if user_id not in self._user_attributes:
            self._user_attributes[user_id] = {}
        self._user_attributes[user_id].update(attributes)
        with self._attr_lock:
            self._attr_buffer.append({"user_id": user_id, "attributes": attributes})
            if len(self._attr_buffer) >= 50:
                self._flush_attributes()

    def get_user_attributes(self, user_id: str) -> dict[str, str]:
        return self._user_attributes.get(user_id, {})

    def get_variant(self, user_id: str, experiment_key: str) -> str | None:
        config = self._poller.config
        if config is None:
            return None

        experiment, layer = config.get_experiment(experiment_key)
        if not experiment:
            return get_variant(user_id, experiment_key, config)

        if user_id in experiment.whitelist:
            return get_variant(user_id, experiment_key, config)

        if experiment.targeting_rules:
            user_attrs = self._user_attributes.get(user_id, {})
            if not evaluate_targeting(experiment.targeting_rules, user_attrs):
                return None

        return get_variant(user_id, experiment_key, config)

    def track(self, user_id: str, event_name: str, experiment_key: str, group_name: str, metadata: dict | None = None):
        self._buffer.track(
            experiment_key=experiment_key,
            group_name=group_name,
            user_id=user_id,
            event_name=event_name,
            metadata=metadata,
        )

    def close(self):
        self._poller.stop()
        self._buffer.stop()
        self._flush_attributes()

    def _flush_attributes(self) -> None:
        with self._attr_lock:
            if not self._attr_buffer:
                return
            batch = self._attr_buffer[:100]

        payload = {"users": batch}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{self._api_url}/api/v1/sdk/attributes",
                    json=payload,
                    headers=headers,
                )
            if resp.status_code in (200, 201, 202):
                with self._attr_lock:
                    self._attr_buffer = self._attr_buffer[len(batch):]
            else:
                logger.warning(f"Attribute upload failed: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Attribute upload error: {e}")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
