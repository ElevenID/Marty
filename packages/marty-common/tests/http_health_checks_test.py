"""Exercise HTTP health checks and their optional stdlib transport boundary."""

import runpy
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

check_http_service = runpy.run_path(
    str(Path(__file__).parents[1] / "marty_common" / "health_checks.py")
)["check_http_service"]


@pytest.fixture(params=[False, True], ids=["httpx", "stdlib"])
def backend(request, monkeypatch):
    if request.param:
        monkeypatch.setitem(sys.modules, "httpx", None)


@pytest.fixture
def gateway():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            redirects = {
                "/redirect": "/ok",
                "/ftp": "ftp://127.0.0.1:1/health",
                "/file": "file:///health",
            }
            self.send_response(302 if self.path in redirects else 200 if self.path == "/ok" else 503)
            if self.path in redirects:
                self.send_header("Location", redirects[self.path])
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_status_and_http_redirect(backend, gateway):
    assert check_http_service(gateway + "/ok")
    assert not check_http_service(gateway + "/unavailable")
    # Preserve urllib's HTTPError behavior for failing statuses.
    assert check_http_service(gateway + "/unavailable", expected_status=503) is (
        sys.modules.get("httpx") is not None
    )
    # httpx intentionally does not follow redirects; stdlib preserves its HTTP redirects.
    assert check_http_service(gateway + "/redirect") is (sys.modules.get("httpx") is None)


def test_non_http_inputs_and_redirects_never_use_other_transports(
    backend, gateway, tmp_path, monkeypatch
):
    transport_calls = []

    def forbidden_transport(self, req):
        transport_calls.append(req.full_url)
        raise AssertionError("Non-HTTP transport must not be invoked")

    monkeypatch.setattr(urllib.request.FTPHandler, "ftp_open", forbidden_transport)
    monkeypatch.setattr(urllib.request.FileHandler, "file_open", forbidden_transport)
    local_file = tmp_path / "health.txt"
    local_file.write_text("private local data", encoding="utf-8")
    for url in (local_file.as_uri(), "ftp://127.0.0.1:1/health", "data:text/plain,healthy"):
        assert not check_http_service(url)
    assert not check_http_service(gateway + "/ftp")
    assert not check_http_service(gateway + "/file")
    assert transport_calls == []
