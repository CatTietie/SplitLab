from splitlab.config_poller import ConfigPoller
from splitlab.event_buffer import EventBuffer
from splitlab.splitter import get_variant


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
        self._poller = ConfigPoller(api_url, poll_interval=poll_interval, api_key=api_key)
        self._buffer = EventBuffer(
            api_url,
            flush_interval=flush_interval,
            buffer_size=buffer_size,
            persistence_path=persistence_path,
            api_key=api_key,
        )
        self._poller.start()
        self._buffer.start()

    def get_variant(self, user_id: str, experiment_key: str) -> str | None:
        config = self._poller.config
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
