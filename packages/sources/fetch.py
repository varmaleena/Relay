"""Allowlisted HTTPS fetch with DNS checks and a pinned, certificate-verified peer."""

import concurrent.futures
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlsplit

MAX_BYTES = 25 * 1024 * 1024
MIMES = {"application/pdf", "text/html", "text/plain"}
_DNS_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_DNS_SLOTS = threading.BoundedSemaphore(2)


class SourceRejected(ValueError):
    pass


def public_ip(value: str) -> str:
    try:
        if "%" in value:
            raise ValueError()
        address = ipaddress.ip_address(value)
        mapped = getattr(address, "ipv4_mapped", None)
        if not address.is_global or (mapped is not None and not mapped.is_global):
            raise ValueError()
        if address.is_multicast or address.is_unspecified:
            raise ValueError()
        return str(address)
    except ValueError:
        raise SourceRejected("Nonpublic source address") from None


def resolve(host: str) -> list[str]:
    if not _DNS_SLOTS.acquire(blocking=False):
        raise SourceRejected("Source DNS capacity unavailable")
    future = _DNS_POOL.submit(socket.getaddrinfo, host, 443, 0, socket.SOCK_STREAM)
    future.add_done_callback(lambda result: _DNS_SLOTS.release())
    try:
        return sorted({str(row[4][0]) for row in future.result(timeout=3)})
    except Exception:
        future.cancel()
        raise SourceRejected("Source DNS unavailable") from None


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        self.tls_context = ssl.create_default_context()
        super().__init__(host, 443, timeout=timeout, context=self.tls_context)
        self.address = address

    def connect(self):
        address = ipaddress.ip_address(self.address)
        raw = socket.socket(
            socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM
        )
        raw.settimeout(self.timeout)
        try:
            raw.connect((self.address, 443))
            if ipaddress.ip_address(raw.getpeername()[0]) != address:
                raise SourceRejected("Source peer changed")
            self.sock = self.tls_context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


@dataclass(frozen=True)
class FetchedSource:
    content: bytes
    mime: str
    final_url: str


class OfficialFetcher:
    def __init__(self, allowed_hosts: set[str], *, resolver=resolve, connection=PinnedHTTPS):
        if not allowed_hosts or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]", h) or ".." in h
            for h in allowed_hosts
        ):
            raise ValueError("Explicit official host allowlist required")
        self.allowed_hosts, self.resolver, self.connection = (
            frozenset(allowed_hosts),
            resolver,
            connection,
        )

    def validate(self, url: str) -> tuple[str, str, str]:
        try:
            parsed = urlsplit(url)
            if (
                len(url) > 4096
                or any(ord(char) <= 32 for char in url)
                or "\\" in url
                or parsed.scheme != "https"
                or parsed.hostname not in self.allowed_hosts
                or parsed.username
                or parsed.password
                or parsed.fragment
                or parsed.port not in {None, 443}
            ):
                raise ValueError()
            forbidden_query = {
                "token",
                "access_token",
                "key",
                "api_key",
                "signature",
                "password",
                "otp",
                "pin",
                "authorization",
            }
            if any(key.casefold() in forbidden_query for key, _ in parse_qsl(parsed.query)):
                raise ValueError()
            addresses = self.resolver(parsed.hostname)
            if not addresses or len(addresses) > 32:
                raise ValueError()
            addresses = [public_ip(address) for address in addresses]
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            return parsed.hostname, addresses[0], target
        except Exception:
            raise SourceRejected("Source URL not allowed") from None

    def fetch(self, url: str) -> FetchedSource:
        deadline = time.monotonic() + 25
        for _ in range(5):
            host, address, target = self.validate(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceRejected("Source fetch timed out")
            connection = self.connection(host, address, min(8, remaining))
            try:
                connection.request(
                    "GET",
                    target,
                    headers={
                        "Accept": "application/pdf,text/html,text/plain",
                        "Accept-Encoding": "identity",
                        "User-Agent": "Relay-SourceIngestion/1.0",
                        "Connection": "close",
                    },
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        raise SourceRejected("Invalid source redirect")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise SourceRejected("Source fetch failed")
                mime = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
                length = response.getheader("Content-Length")
                if (
                    mime not in MIMES
                    or response.getheader("Content-Encoding") not in {None, "identity"}
                    or (length is not None and (not length.isdigit() or int(length) > MAX_BYTES))
                ):
                    raise SourceRejected("Source format or size rejected")
                content = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SourceRejected("Source fetch timed out")
                    if connection.sock:
                        connection.sock.settimeout(min(8, remaining))
                    chunk = response.read(min(65536, MAX_BYTES + 1 - len(content)))
                    if not chunk:
                        break
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise SourceRejected("Source size exceeded")
                if not content:
                    raise SourceRejected("Empty source")
                return FetchedSource(bytes(content), mime, url)
            except SourceRejected:
                raise
            except Exception:
                raise SourceRejected("Source fetch unavailable") from None
            finally:
                connection.close()
        raise SourceRejected("Source redirect limit exceeded")
