"""Server lifecycle: liveness by connection, not by a stale pidfile."""

import socket
import threading
from functools import partial
from http.server import ThreadingHTTPServer

import pytest

from lcsr import server as srv


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_is_up_is_false_for_a_closed_port():
    assert srv.is_up("127.0.0.1", free_port()) is False


def test_is_up_is_true_while_a_server_listens():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(srv.Handler))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        assert srv.is_up("127.0.0.1", port) is True
    finally:
        httpd.shutdown()
    assert srv.is_up("127.0.0.1", port) is False


def test_stop_reports_false_when_the_pidfile_is_stale(tmp_path, monkeypatch):
    """A pidfile outlives a crash, so it is a claim about the past. stop() must
    say so rather than pretending it killed something."""
    monkeypatch.setattr(srv, "PIDFILE", tmp_path / "server.pid")
    srv.PIDFILE.write_text("999999", encoding="utf-8")   # certainly not running
    assert srv.stop() is False
    assert not srv.PIDFILE.exists(), "stale pidfile should be cleaned up"


def test_stop_reports_false_with_no_pidfile(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "PIDFILE", tmp_path / "server.pid")
    assert srv.stop() is False
