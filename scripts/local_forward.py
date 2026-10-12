#!/usr/bin/env python3
"""Loopback HTTP forward proxy; HTTPS/WSS use opaque CONNECT tunnels.

Python 3.9+, standard library only. Raw sockets deliberately ignore HTTP_PROXY
and HTTPS_PROXY in the environment, so the direct-network mode cannot recurse.
"""
import argparse
import select
import socket
import socketserver
import time
from urllib.parse import urlsplit

MAX_HEADER = 65536


def destination(authority):
    parsed = urlsplit("//" + authority)
    if (not parsed.hostname or parsed.port is None or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("CONNECT requires host:port (IPv6: [address]:port)")
    return parsed.hostname, parsed.port


def read_header(sock):
    data = bytearray()
    while True:
        chunk = sock.recv(8192)
        if not chunk:
            raise ValueError("Incomplete request headers")
        data.extend(chunk)
        end = data.find(b"\r\n\r\n")
        if end >= 0:
            if end + 4 > MAX_HEADER:
                raise ValueError("Request headers too large")
            return bytes(data[:end]), bytes(data[end + 4:])
        if len(data) > MAX_HEADER:
            raise ValueError("Request headers too large")


def bridge(client, upstream, idle_timeout):
    """Relay streams with half-close support; preserve SSE and upgraded sockets."""
    readers = [client, upstream]
    last_activity = time.monotonic()
    while readers:
        remaining = idle_timeout - (time.monotonic() - last_activity)
        if remaining <= 0:
            return
        ready, _, _ = select.select(readers, [], [], min(remaining, 1))
        for source in ready:
            target = upstream if source is client else client
            chunk = source.recv(65536)
            if not chunk:
                readers.remove(source)
                try:
                    target.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                continue
            target.sendall(chunk)
            last_activity = time.monotonic()


def http_request(header):
    lines = header.decode("iso-8859-1").split("\r\n")
    method, target, version = lines[0].split(" ")
    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise ValueError("Only HTTP/1.0 and HTTP/1.1 are supported")
    headers = []
    for line in lines[1:]:
        if ":" not in line or line.startswith((" ", "\t")):
            raise ValueError("Invalid header")
        name, value = line.split(":", 1)
        headers.append((name, value.strip()))
    lower = [name.lower() for name, _ in headers]
    if lower.count("content-length") > 1 or (
            "content-length" in lower and "transfer-encoding" in lower):
        raise ValueError("Ambiguous request body framing")
    if method == "CONNECT":
        host, port = destination(target)
        return host, port, None
    parsed = urlsplit(target)
    if parsed.scheme not in ("http", "ws") or not parsed.hostname:
        raise ValueError("Use an absolute http:// URL or CONNECT for HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not supported")
    host, port = parsed.hostname, parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    upgrade = any(name.lower() == "upgrade" and value.lower() == "websocket"
                  for name, value in headers)
    connection_tokens = set()
    for name, value in headers:
        if name.lower() == "connection":
            connection_tokens.update(token.strip().lower() for token in value.split(","))
    excluded = {"proxy-authorization", "proxy-connection", "host", "connection"}
    excluded.update(connection_tokens - {"upgrade", "transfer-encoding"})
    host_header = "[" + host + "]" if ":" in host else host
    if port != 80:
        host_header += ":" + str(port)
    output = [f"{method} {path} {version}", "Host: " + host_header]
    output.extend(name + ": " + value for name, value in headers
                  if name.lower() not in excluded)
    output.append("Connection: Upgrade" if upgrade else "Connection: close")
    return host, port, ("\r\n".join(output) + "\r\n\r\n").encode("iso-8859-1")


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = None
        established = False
        try:
            self.request.settimeout(self.server.connect_timeout)
            header, initial_body = read_header(self.request)
            host, port, rewritten = http_request(header)
            upstream = socket.create_connection((host, port), self.server.connect_timeout)
            upstream.settimeout(self.server.connect_timeout)
            if rewritten is None:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                upstream.sendall(rewritten)
            established = True
            if initial_body:
                upstream.sendall(initial_body)
            bridge(self.request, upstream, self.server.idle_timeout)
        except (OSError, ValueError) as error:
            if not established:
                code = 400 if isinstance(error, ValueError) else 502
                body = b"Invalid proxy request\n" if code == 400 else b"Upstream connection failed\n"
                response = (f"HTTP/1.1 {code} Proxy Error\r\nConnection: close\r\n"
                            f"Content-Length: {len(body)}\r\n\r\n").encode() + body
                try:
                    self.request.sendall(response)
                except OSError:
                    pass
            if self.server.verbose:
                print("Proxy connection ended:", type(error).__name__, flush=True)
        finally:
            if upstream is not None:
                upstream.close()


class ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11450)
    parser.add_argument("--connect-timeout", type=float, default=30)
    parser.add_argument("--idle-timeout", type=float, default=3600)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.connect_timeout <= 0 or args.idle_timeout <= 0:
        parser.error("Use a valid port and positive timeouts")
    try:
        with ProxyServer(("127.0.0.1", args.port), ProxyHandler) as server:
            server.connect_timeout = args.connect_timeout
            server.idle_timeout = args.idle_timeout
            server.verbose = args.verbose
            print(f"Local HTTP proxy: http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
            print("Uses this computer's direct DNS/routing; keep this window open.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy stopped.")
    except OSError as error:
        parser.exit(1, f"Cannot start proxy: {error}\n")


if __name__ == "__main__":
    main()
