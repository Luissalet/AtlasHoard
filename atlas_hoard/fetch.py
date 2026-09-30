"""Fetching a page safely: http(s) only, social networks refused, no loopback/LAN targets by default.

The capture never executes JavaScript: it downloads bytes and the extractor reads them as text.
Redirects are followed by hand so every hop is checked against the same rules.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from .errors import AtlasError, Refused

# Hosts whose pages are personal profiles and feeds. Atlas does not scrape them; the user can paste
# what they are entitled to use as a text source instead.
SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "fb.me", "instagram.com", "twitter.com", "x.com", "t.co", "tiktok.com",
    "linkedin.com", "reddit.com", "snapchat.com", "threads.net", "pinterest.com", "tumblr.com",
    "vk.com", "weibo.com", "telegram.me", "t.me", "whatsapp.com", "discord.com", "discord.gg",
    "youtube.com", "youtu.be", "bsky.app", "mastodon.social",
)
MAX_REDIRECTS = 5


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    error: str | None = None


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def is_social_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in SOCIAL_HOSTS)


def _is_private_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # unresolvable: the request itself will fail with a clear error
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return True
    return False


def check_url(url: str, *, allow_private: bool = False) -> str:
    """Validate a capture target; return the URL or raise. Used by every fetcher and by the tests."""
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AtlasError("Only http(s) URLs can be captured.")
    host = parts.hostname.lower().rstrip(".")
    if is_social_host(host):
        raise Refused(f"{host} is a social network: Atlas does not capture social profiles or feeds. "
                      "Add the text you may use manually as a text source (kind=text, with the URL as reference).")
    if not allow_private and (host in ("localhost",) or host.endswith(".localhost") or _is_private_address(host)):
        raise Refused(f"{host} resolves to a local or private address; URL capture only reaches the public web "
                      "(set ATLAS_ALLOW_PRIVATE_URLS=1 to allow it).")
    return parts.geturl()


class HttpFetcher:
    """httpx-based fetcher with a byte cap and per-hop URL checks."""

    def __init__(self, *, timeout_s: float, max_bytes: int, user_agent: str, allow_private: bool):
        self.timeout_s, self.max_bytes, self.user_agent, self.allow_private = timeout_s, max_bytes, user_agent, allow_private

    def fetch(self, url: str) -> FetchResult:
        current = check_url(url, allow_private=self.allow_private)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5"}
        try:
            with httpx.Client(timeout=self.timeout_s, follow_redirects=False, headers=headers) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    with client.stream("GET", current) as response:
                        if response.is_redirect and response.headers.get("location"):
                            current = check_url(urljoin(current, response.headers["location"]), allow_private=self.allow_private)
                            continue
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            chunks.append(chunk)
                            if size > self.max_bytes:
                                break
                        return FetchResult(url, current, response.status_code, response.headers.get("content-type", ""),
                                           b"".join(chunks)[: self.max_bytes])
                return FetchResult(url, current, 0, "", b"", error="Too many redirects.")
        except httpx.HTTPError as error:
            return FetchResult(url, current, 0, "", b"", error=f"{type(error).__name__}: {error}")
