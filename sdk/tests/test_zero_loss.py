"""Event buffer zero-loss test.

Validates that events are not lost even when the process crashes
(simulated by not calling close()) — WAL persists them to disk.
"""
import json
import os
import tempfile
import time
import threading
from unittest.mock import patch, MagicMock

from splitlab.event_buffer import EventBuffer


def test_wal_persistence_on_track():
    """Every track() call should append to the WAL file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        wal_path = f.name

    try:
        buffer = EventBuffer(
            api_url="http://fake:8000",
            flush_interval=999,  # don't auto-flush
            persistence_path=wal_path,
        )
        buffer.start()

        for i in range(50):
            buffer.track(
                experiment_key="exp1",
                group_name="control",
                user_id=f"user_{i}",
                event_name="purchase",
            )

        # Don't call stop/flush — simulate crash
        buffer._stop_event.set()
        buffer._thread.join(timeout=2)

        # Verify WAL has all 50 events
        with open(wal_path) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 50, f"Expected 50 lines in WAL, got {len(lines)}"

        # Verify each line is valid JSON
        for line in lines:
            data = json.loads(line)
            assert "user_id" in data
            assert "event_name" in data
    finally:
        os.unlink(wal_path)


def test_recovery_from_wal():
    """New buffer instance should recover events from WAL and flush them."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        wal_path = f.name

    try:
        # Write WAL manually (simulating previous crash)
        events = []
        for i in range(30):
            ev = {
                "experiment_key": "exp1",
                "group_name": "treatment",
                "user_id": f"user_{i}",
                "event_name": "signup",
                "metadata": None,
                "event_time": "2026-06-08T10:00:00+00:00",
            }
            events.append(ev)
        with open(wal_path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        # Create new buffer that should recover
        buffer = EventBuffer(
            api_url="http://fake:8000",
            flush_interval=999,
            persistence_path=wal_path,
        )
        # Don't start the flush loop, just check recovery
        buffer._recover_persisted()

        assert len(buffer._buffer) == 30
        assert buffer._buffer[0].user_id == "user_0"
        assert buffer._buffer[0].event_name == "signup"
    finally:
        os.unlink(wal_path)


def test_wal_cleared_after_successful_flush():
    """WAL file should be removed after successful flush."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        wal_path = f.name

    try:
        buffer = EventBuffer(
            api_url="http://fake:8000",
            flush_interval=999,
            persistence_path=wal_path,
        )
        buffer.start()

        buffer.track("exp1", "control", "user_1", "click")

        assert os.path.exists(wal_path)

        # Mock successful HTTP response
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=mock_response)))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            buffer.flush()

        assert not os.path.exists(wal_path), "WAL should be cleared after successful flush"
        assert len(buffer._buffer) == 0
    finally:
        if os.path.exists(wal_path):
            os.unlink(wal_path)
        buffer._stop_event.set()


def test_events_retained_on_flush_failure():
    """Events should stay in buffer on HTTP failure."""
    buffer = EventBuffer(
        api_url="http://fake:8000",
        flush_interval=999,
    )
    buffer.start()

    buffer.track("exp1", "control", "user_1", "click")

    # Mock failed HTTP response
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__ = MagicMock(
            return_value=MagicMock(post=MagicMock(side_effect=Exception("connection refused")))
        )
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        buffer.flush()

    assert len(buffer._buffer) == 1, "Events should remain in buffer on failure"
    buffer._stop_event.set()


def test_zero_loss_full_scenario():
    """End-to-end: track events, simulate crash, recover, verify count."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        wal_path = f.name

    try:
        n_events = 200

        # Phase 1: Track events with no flush (simulate slow/failing network)
        buffer1 = EventBuffer(
            api_url="http://fake:8000",
            flush_interval=999,
            persistence_path=wal_path,
        )
        buffer1.start()

        for i in range(n_events):
            buffer1.track("exp1", "control", f"user_{i}", "purchase")

        # Simulate crash
        buffer1._stop_event.set()
        buffer1._thread.join(timeout=2)

        # Verify WAL completeness
        with open(wal_path) as f:
            wal_lines = [l for l in f if l.strip()]
        assert len(wal_lines) == n_events, f"WAL has {len(wal_lines)}, expected {n_events}"

        # Phase 2: New buffer recovers
        buffer2 = EventBuffer(
            api_url="http://fake:8000",
            flush_interval=999,
            persistence_path=wal_path,
        )
        buffer2._recover_persisted()
        assert len(buffer2._buffer) == n_events, f"Recovery got {len(buffer2._buffer)}, expected {n_events}"
    finally:
        if os.path.exists(wal_path):
            os.unlink(wal_path)
