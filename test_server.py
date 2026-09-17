"""
test_server.py - Integration test for server endpoints.
"""

import json
import threading
import time
import requests
import pytest
from server import ThreadedHTTPServer, AgentRequestHandler


@pytest.fixture(scope="module")
def live_server():
    server = ThreadedHTTPServer(("localhost", 8999), AgentRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)  # Wait for server startup
    yield "http://localhost:8999"
    server.shutdown()
    server.server_close()


def test_server_serves_html(live_server):
    resp = requests.get(f"{live_server}/")
    assert resp.status_code == 200
    assert "agent / core-loop" in resp.text or "the-brain" in resp.text


def test_server_status_endpoint(live_server):
    resp = requests.get(f"{live_server}/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert len(data["tools"]) == 4


def test_server_files_endpoint(live_server):
    resp = requests.get(f"{live_server}/api/files")
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert isinstance(data["files"], list)
