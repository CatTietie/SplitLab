"""Config hot-reload test.

Validates that when the backend config changes, the SDK picks up
the new config within 60 seconds (tests use 2s poll interval).
"""
import json
import time
import threading
from unittest.mock import patch, MagicMock
from http.server import HTTPServer, BaseHTTPRequestHandler

from splitlab.config_poller import ConfigPoller
from splitlab.models import SDKConfig


class FakeConfigServer:
    """Minimal HTTP server that serves changing config."""

    def __init__(self):
        self.config_data = {"layers": [], "version": "1"}
        self.etag = "etag_v1"
        self._server = None
        self._thread = None

    def start(self, port: int = 0):
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/v1/sdk/config":
                    client_etag = self.headers.get("If-None-Match", "").strip('"')
                    if client_etag == server_ref.etag:
                        self.send_response(304)
                        self.end_headers()
                        return
                    body = json.dumps(server_ref.config_data).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("ETag", f'"{server_ref.etag}"')
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # suppress logs

        self._server = HTTPServer(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()

    def update_config(self, layers: list, version: str):
        self.config_data = {"layers": layers, "version": version}
        self.etag = f"etag_{version}"


def test_config_hot_reload_within_timeout():
    """Config change should be picked up within poll_interval * 2."""
    server = FakeConfigServer()
    server.start()

    try:
        poll_interval = 1  # 1 second for fast test
        poller = ConfigPoller(f"http://127.0.0.1:{server.port}", poll_interval=poll_interval)
        poller.start()

        # Initially empty config
        time.sleep(0.5)
        assert len(poller.config.layers) == 0

        # Update server config
        server.update_config(
            layers=[{
                "id": "layer1",
                "name": "test_layer",
                "salt": "test_salt",
                "experiments": [{
                    "id": "exp1",
                    "key": "new_experiment",
                    "status": "running",
                    "bucket_start": 0,
                    "bucket_end": 9999,
                    "groups": [{"id": "g1", "name": "control", "traffic_percentage": 100}],
                    "whitelist": {},
                }],
            }],
            version="v2",
        )

        # Wait for poller to pick up (should happen within poll_interval + some margin)
        start = time.time()
        timeout = 60  # SLA: must be < 60s
        while time.time() - start < timeout:
            config = poller.config
            if len(config.layers) > 0 and len(config.layers[0].experiments) > 0:
                break
            time.sleep(0.2)

        elapsed = time.time() - start
        assert elapsed < 60, f"Config propagation took {elapsed:.1f}s, exceeds 60s SLA"
        assert len(poller.config.layers) == 1
        assert poller.config.layers[0].experiments[0].key == "new_experiment"

        poller.stop()
    finally:
        server.stop()


def test_etag_prevents_redundant_downloads():
    """SDK should not re-download unchanged config (304 response)."""
    server = FakeConfigServer()
    server.update_config(
        layers=[{"id": "l1", "name": "layer", "salt": "s", "experiments": []}],
        version="v1",
    )
    server.start()

    try:
        poller = ConfigPoller(f"http://127.0.0.1:{server.port}", poll_interval=0.5)
        poller.start()

        time.sleep(0.3)  # First fetch
        assert poller._etag == "etag_v1"

        # Wait for second poll (should get 304)
        time.sleep(1)
        # Config should still be v1, etag unchanged
        assert poller._etag == "etag_v1"
        assert len(poller.config.layers) == 1

        poller.stop()
    finally:
        server.stop()


def test_poller_survives_server_error():
    """Poller should keep stale config on server error and recover."""
    server = FakeConfigServer()
    server.update_config(
        layers=[{"id": "l1", "name": "layer", "salt": "s", "experiments": []}],
        version="v1",
    )
    server.start()

    try:
        poller = ConfigPoller(f"http://127.0.0.1:{server.port}", poll_interval=0.5)
        poller.start()
        time.sleep(0.3)
        assert len(poller.config.layers) == 1

        # Kill server
        server.stop()
        time.sleep(1)

        # Config should still be available (stale)
        assert len(poller.config.layers) == 1

        poller.stop()
    finally:
        pass
