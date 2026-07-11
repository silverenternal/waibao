"""SMTP / SendGrid 邮件 provider."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import NotifyMessage, NotifyProvider, NotifyResult


class SMTPProvider(NotifyProvider):
    """通用 SMTP (可对接 SendGrid / Mailgun / 自建 SMTP)."""

    channel = "smtp"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
        *,
        use_tls: bool = True,
        rate_per_sec: float = 5.0,
        burst: int = 10,
    ) -> None:
        self.host = host or os.getenv("SMTP_HOST", "")
        self.port = port or int(os.getenv("SMTP_PORT", "587"))
        self.username = username or os.getenv("SMTP_USERNAME", "")
        self.password = password or os.getenv("SMTP_PASSWORD", "")
        self.from_addr = from_addr or os.getenv("SMTP_FROM", self.username)
        self.use_tls = use_tls
        if not self.host or not self.from_addr:
            raise InvalidRequestError(
                "SMTP_HOST / SMTP_FROM 必须配置", provider="smtp"
            )
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _build_message(self, msg: NotifyMessage) -> EmailMessage:
        m = EmailMessage()
        m["From"] = self.from_addr
        m["To"] = ", ".join(msg.to)
        if msg.subject:
            m["Subject"] = msg.subject
        if msg.html:
            m.set_content(msg.body or "")
            m.add_alternative(msg.html, subtype="html")
        else:
            m.set_content(msg.body or "")
        if msg.attachments:
            for filename, content, mime in msg.attachments:
                maintype, subtype = mime.split("/", 1)
                m.add_attachment(
                    content, maintype=maintype, subtype=subtype, filename=filename
                )
        return m

    @with_resilience(provider="smtp", method="send", rate_per_sec=5.0, burst=10)
    async def send(self, message: NotifyMessage) -> NotifyResult:
        """SMTP 同步发,在线程池中执行避免阻塞事件循环."""
        import asyncio

        def _do_send() -> str:
            email = self._build_message(message)
            context = ssl.create_default_context() if self.use_tls else None
            with smtplib.SMTP(self.host, self.port, timeout=30) as s:
                s.ehlo()
                if self.use_tls:
                    s.starttls(context=context)
                    s.ehlo()
                if self.username:
                    s.login(self.username, self.password)
                s.send_message(email)
            return email["Message-ID"] or ""

        try:
            msg_id = await asyncio.to_thread(_do_send)
        except Exception as exc:
            raise ProviderError(str(exc), provider="smtp") from exc
        return NotifyResult(
            success=True,
            channel=self.channel,
            message_id=msg_id or None,
        )
