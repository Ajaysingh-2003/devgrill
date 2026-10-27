"""Sending email through a port: SMTP (Mailpit in dev), or memory in tests.

The digest is the only email so far. Its pause link carries a signed token, so one tap pauses
it without signing in (and a mail client's one-click unsubscribe, RFC 8058, can POST to it).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import smtplib
import uuid
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str
    #: Extra headers (List-Unsubscribe and friends).
    headers: dict[str, str] = field(default_factory=lambda: {})


class Mailer(Protocol):
    async def send(self, mail: Mail, /) -> None: ...


class SmtpMailer:
    """Plain SMTP: enough for Mailpit locally and a relay later (a provider is an adapter)."""

    def __init__(self, host: str, port: int, sender: str) -> None:
        self.host, self.port, self.sender = host, port, sender

    def _send(self, mail: Mail) -> None:
        # Long ASCII headers (List-Unsubscribe with its token) must not be RFC 2047-encoded.
        message = EmailMessage(policy=policy.SMTP.clone(max_line_length=998))
        message["From"] = self.sender
        message["To"] = mail.to
        message["Subject"] = mail.subject
        for name, value in mail.headers.items():
            message[name] = value
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.send_message(message)

    async def send(self, mail: Mail, /) -> None:
        await asyncio.to_thread(self._send, mail)


class MemoryMailer:
    """Keeps what was sent, for tests."""

    def __init__(self) -> None:
        self.sent: list[Mail] = []

    async def send(self, mail: Mail, /) -> None:
        self.sent.append(mail)


_PAUSE = b"digest-pause:"


def pause_token(user_id: uuid.UUID, secret: str) -> str:
    """A token that pauses this user's digest (and nothing else)."""
    if not secret:
        raise ValueError("no signing secret configured")
    sig = hmac.new(secret.encode(), _PAUSE + user_id.bytes, hashlib.sha256).digest()
    return f"{user_id}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def verify_pause_token(token: str, secret: str) -> uuid.UUID | None:
    """The user the token is for, or None when it isn't one of ours."""
    try:
        raw_id, _ = token.split(".", 1)
        user_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    if not secret or not hmac.compare_digest(pause_token(user_id, secret), token):
        return None
    return user_id
