"""Offline behavioral tests; all listeners use ephemeral loopback ports."""
import contextlib
import http.server
import socket
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import local_forward
import configure_remote
import codex_with_proxy


@contextlib.contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def receive_header(sock):
    return local_forward.read_header(sock)


def receive_all(sock):
    chunks = []
    while True:
        data = sock.recv(65536)
        if not data:
            return b"".join(chunks)
        chunks.append(data)


class Origin(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for index, item in enumerate((b"data: first\n\n", b"data: second\n\n")):
                self.wfile.write(f"{len(item):x}\r\n".encode() + item + b"\r\n")
                self.wfile.flush()
                if index == 0:
                    self.server.release_stream.wait(3)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.end_headers()
            self.wfile.write(self.rfile.read(4))
            self.wfile.flush()
            self.close_connection = True
            return
        body = self.path.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            body = bytearray()
            while True:
                length = int(self.rfile.readline().strip(), 16)
                if not length:
                    self.rfile.readline()
                    break
                body.extend(self.rfile.read(length))
                self.rfile.read(2)
            body = bytes(body)
        else:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = contextlib.ExitStack()
        proxy = local_forward.ProxyServer(("127.0.0.1", 0), local_forward.ProxyHandler)
        proxy.connect_timeout = 3
        proxy.idle_timeout = 5
        proxy.verbose = False
        cls.proxy_port = cls.stack.enter_context(running(proxy))
        origin = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        origin.release_stream = threading.Event()
        cls.origin = origin
        cls.origin_port = cls.stack.enter_context(running(origin))
        cls.echo_port = cls.stack.enter_context(running(local_forward.ProxyServer(("127.0.0.1", 0), Echo)))

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def exchange(self, request):
        with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=4) as client:
            client.sendall(request)
            return receive_all(client)

    def test_get_query_and_host(self):
        response = self.exchange(f"GET http://127.0.0.1:{self.origin_port}/hello?a=1 HTTP/1.1\r\nHost: invalid.example\r\n\r\n".encode())
        self.assertIn(b"200 OK", response)
        self.assertTrue(response.endswith(b"/hello?a=1"))

    def test_post_body_survives_header_buffering(self):
        body = b"research-data" * 20000
        header = f"POST http://127.0.0.1:{self.origin_port}/upload HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n".encode()
        response = self.exchange(header + body)
        self.assertEqual(response.split(b"\r\n\r\n", 1)[1], body)

    def test_chunked_request(self):
        request = f"POST http://127.0.0.1:{self.origin_port}/upload HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n".encode()
        response = self.exchange(request + b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
        self.assertTrue(response.endswith(b"hello world"))

    def test_stream_arrives_before_end(self):
        with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=4) as client:
            client.sendall(f"GET http://127.0.0.1:{self.origin_port}/stream HTTP/1.1\r\n\r\n".encode())
            header, body = receive_header(client)
            self.assertIn(b"Transfer-Encoding: chunked", header)
            while b"data: first" not in body:
                body += client.recv(1024)
            self.assertNotIn(b"0\r\n\r\n", body)
            self.origin.release_stream.set()
            rest = receive_all(client)
            self.assertIn(b"data: second", body + rest)

    def test_connect_binary_and_early_payload(self):
        payload = b"\x16\x03\x01\x00\x08opaque\x00\xff"
        with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=4) as client:
            client.sendall(f"CONNECT 127.0.0.1:{self.echo_port} HTTP/1.1\r\n\r\n".encode() + payload)
            header, echoed = receive_header(client)
            self.assertIn(b"200 Connection Established", header)
            while len(echoed) < len(payload):
                echoed += client.recv(1024)
            self.assertEqual(echoed, payload)
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(receive_all(client), b"")

    def test_websocket_upgrade_and_bytes(self):
        with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=4) as client:
            client.sendall(f"GET http://127.0.0.1:{self.origin_port}/ws HTTP/1.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n".encode())
            header, extra = receive_header(client)
            self.assertIn(b"101 Switching Protocols", header)
            client.sendall(b"ping")
            self.assertEqual(extra + client.recv(4), b"ping")

    def test_invalid_framing_and_upstream_failure(self):
        response = self.exchange(b"POST http://127.0.0.1/ HTTP/1.1\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n")
        self.assertIn(b"400 Proxy Error", response)
        with socket.socket() as unlistened:
            unlistened.bind(("127.0.0.1", 0))
            port = unlistened.getsockname()[1]
            response = self.exchange(f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n".encode())
            self.assertIn(b"502 Proxy Error", response)

    def test_ipv6_authority_parser(self):
        self.assertEqual(local_forward.destination("[::1]:443"), ("::1", 443))
        with self.assertRaises(ValueError):
            local_forward.destination("user:password@example.com:443")


class ConfigurationTests(unittest.TestCase):
    def test_backup_preservation_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = '# keep this\nCUSTOM_OPTION="preserve me"\nHTTP_PROXY="old"\n'
            path.write_text(original, encoding="utf-8")
            backup = configure_remote.configure(path, 17891)
            self.assertEqual(backup.read_text(encoding="utf-8"), original)
            self.assertIn('CUSTOM_OPTION="preserve me"', path.read_text(encoding="utf-8"))
            self.assertIsNone(configure_remote.configure(path, 17891))
            self.assertEqual(len(list(Path(directory).glob(".env.backup-*"))), 1)
            values = codex_with_proxy.load_proxy(path)
            self.assertEqual(values["HTTPS_PROXY"], "http://127.0.0.1:17891")
            self.assertNotIn("CUSTOM_OPTION", values)

    def test_dry_run_does_not_write_and_launcher_does_not_eval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".codex" / ".env"
            configure_remote.configure(path, 17891, dry_run=True)
            self.assertFalse(path.parent.exists())
            path.parent.mkdir()
            path.write_text(configure_remote.render('MALICIOUS=$(touch injected)\n', 17891), encoding="utf-8")
            values = codex_with_proxy.load_proxy(path)
            self.assertNotIn("MALICIOUS", values)
            self.assertFalse((Path(directory) / "injected").exists())

    def test_launcher_rejects_nonloopback_and_missing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('HTTP_PROXY="http://example.com:7890"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                codex_with_proxy.load_proxy(path)
            path.write_text("OTHER=1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                codex_with_proxy.load_proxy(path)


if __name__ == "__main__":
    unittest.main()
