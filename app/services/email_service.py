from email.message import EmailMessage
from html import escape

from app.config import Settings
from app.core.logging import get_app_logger
from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest


def build_owner_message(settings: Settings, data: ContactRequest, analysis: AIAnalysis) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = settings.owner_email
    msg["Subject"] = f"New contact [{analysis.priority}] from {data.name}"
    msg.set_content(
        f"Name: {data.name}\nEmail: {data.email}\nPhone: {data.phone}\n\n"
        f"Message:\n{data.comment}\n\n"
        f"--- AI analysis (available={analysis.ai_available}) ---\n"
        f"Sentiment: {analysis.sentiment}\nCategory: {analysis.category}\n"
        f"Priority: {analysis.priority}\n\nSuggested reply:\n{analysis.suggested_reply}"
    )
    return msg


def build_user_message(settings: Settings, data: ContactRequest) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = data.email
    msg["Subject"] = "We received your message"
    msg.set_content(
        f"Hi {data.name},\n\nThanks for reaching out — we received your message "
        f"and will reply soon.\n\nYour message:\n{data.comment}\n\n— The team"
    )
    return msg


class EmailService:
    def __init__(self, settings: Settings, sender=None):
        self._settings = settings
        self._sender = sender or self._default_sender

    async def _default_sender(self, message: EmailMessage) -> None:
        import aiosmtplib
        await aiosmtplib.send(
            message,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_user,
            password=self._settings.smtp_password,
            start_tls=True,
        )

    async def _send(self, message: EmailMessage, kind: str) -> None:
        if not self._settings.email_configured:
            get_app_logger().info("", extra={"event": {"kind": "email_skipped", "reason": "not_configured", "mail": kind}})
            return
        try:
            await self._sender(message)
            get_app_logger().info("", extra={"event": {"kind": "email_sent", "mail": kind, "to": message["To"]}})
        except Exception as exc:  # noqa: BLE001 — never break the request on email failure
            get_app_logger().error("", extra={"event": {"kind": "email_failed", "mail": kind, "type": type(exc).__name__, "detail": str(exc)}})

    async def send_owner(self, data: ContactRequest, analysis: AIAnalysis) -> None:
        await self._send(build_owner_message(self._settings, data, analysis), "owner")

    async def send_user_copy(self, data: ContactRequest) -> None:
        await self._send(build_user_message(self._settings, data), "user_copy")
