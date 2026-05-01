"""Shared fixtures for auntiepypi tests.

Provides an in-process HTTP server fixture so probe tests don't depend on
any external port/process. Stdlib only — no aiohttp/Flask/etc.

Also exposes a session-scoped self-signed RSA cert/key fixture for
tls/auth tests. Production code never imports ``cryptography``; the
fixture generates a fresh 1-day cert per test session so no PEM ever
lives on disk in the repo.
"""

from __future__ import annotations

import datetime
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Iterator

import pytest

# Type for a handler-factory: takes a status code, returns a request-handler class.
HandlerFactory = Callable[[int], type[BaseHTTPRequestHandler]]


def _handler_for(status: int) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server contract
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}\n')

        def log_message(self, fmt: str, *args: object) -> None:  # noqa: A002
            # Silence the default stderr access log.
            return

    return _Handler


@pytest.fixture
def fake_http_server() -> Iterator[Callable[[int], tuple[str, int]]]:
    """Yield a callable: ``start(status_code) -> (host, port)``.

    Multiple servers can be started in one test. All are torn down on exit.
    """
    servers: list[HTTPServer] = []

    def start(status: int = 200) -> tuple[str, int]:
        server = HTTPServer(("127.0.0.1", 0), _handler_for(status))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        host, port = server.server_address[0], server.server_address[1]
        return host, port

    yield start

    for s in servers:
        s.shutdown()
        s.server_close()


# --------- v0.7.0 TLS fixtures (session-scoped) ---------


@pytest.fixture(scope="session")
def tls_cert_pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Generate a self-signed RSA cert + key pair, valid for 1 day.

    Returns ``(cert_path, key_path)`` — both PEM-encoded, paired,
    suitable for ``ssl.SSLContext.load_cert_chain``. Session-scoped so
    a single test run only pays the keygen cost once.

    The fixture imports ``cryptography`` lazily so projects that skip
    the TLS test suite don't pay the import cost.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    out_dir = tmp_path_factory.mktemp("tls")
    cert_path = out_dir / "cert.pem"
    key_path = out_dir / "key.pem"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "auntiepypi-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path
