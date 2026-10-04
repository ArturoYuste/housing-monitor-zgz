"""IMAP inbox reader for Idealista (and other) alert emails."""

from __future__ import annotations

import email
import imaplib
import os
import re
from dataclasses import dataclass
from email.header import decode_header
from typing import Iterable


# Avoid nested quote conflicts in character classes by using alternation.
URL_TAIL = r"[A-Za-z0-9_./?&=%+#\-]+"
IDEALISTA_URL_RE = re.compile(
    rf"https?://(?:www\.)?idealista\.com/{URL_TAIL}",
    re.IGNORECASE,
)
GENERIC_PORTAL_URL_RE = re.compile(
    rf"https?://(?:www\.)?(?:fotocasa\.es|habitaclia\.com|pisos\.com)/{URL_TAIL}",
    re.IGNORECASE,
)


@dataclass
class AlertLink:
    url: str
    portal: str
    subject: str
    message_id: str


def imap_enabled() -> bool:
    return os.getenv("IMAP_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    chunks: list[str] = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            chunks.append(chunk)
    return "".join(chunks)


def _detect_portal(url: str) -> str:
    lower = url.lower()
    if "idealista.com" in lower:
        return "idealista"
    if "fotocasa.es" in lower:
        return "fotocasa"
    if "habitaclia.com" in lower:
        return "habitaclia"
    if "pisos.com" in lower:
        return "pisos.com"
    return "unknown"


def extract_alert_links(subject: str, body: str, message_id: str) -> list[AlertLink]:
    """Extract property URLs from an alert email body."""
    found: list[AlertLink] = []
    seen: set[str] = set()
    for pattern in (IDEALISTA_URL_RE, GENERIC_PORTAL_URL_RE):
        for match in pattern.findall(body or ""):
            url = match.rstrip(").,;>")
            if url in seen:
                continue
            seen.add(url)
            found.append(
                AlertLink(
                    url=url,
                    portal=_detect_portal(url),
                    subject=subject,
                    message_id=message_id,
                )
            )
    return found


def fetch_alert_links(limit: int = 30) -> list[AlertLink]:
    """Connect to IMAP and collect recent alert links.

    Requires IMAP_* env vars. Returns an empty list when IMAP is disabled.
    """
    if not imap_enabled():
        return []

    host = os.getenv("IMAP_HOST", "imap.gmail.com")
    port = int(os.getenv("IMAP_PORT", "993"))
    user = os.getenv("IMAP_USER", "")
    password = os.getenv("IMAP_PASSWORD", "")
    folder = os.getenv("IMAP_FOLDER", "INBOX")
    if not user or not password:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD are required when IMAP_ENABLED=true")

    links: list[AlertLink] = []
    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(user, password)
        client.select(folder)
        status, data = client.search(None, "ALL")
        if status != "OK":
            return []
        ids = data[0].split()
        for message_id in reversed(ids[-limit:]):
            status, payload = client.fetch(message_id, "(RFC822)")
            if status != "OK" or not payload or not payload[0]:
                continue
            raw = payload[0][1]
            msg = email.message_from_bytes(raw)
            subject = _decode_mime(msg.get("Subject"))
            body = _message_body(msg)
            links.extend(extract_alert_links(subject, body, message_id.decode()))
    return links


def _message_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        chunks: list[str] = []
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
        return "\n".join(chunks)
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def unique_urls(links: Iterable[AlertLink]) -> list[AlertLink]:
    seen: set[str] = set()
    ordered: list[AlertLink] = []
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        ordered.append(link)
    return ordered
