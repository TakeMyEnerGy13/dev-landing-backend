import pytest

from app.config import Settings
from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest
from app.services.email_service import EmailService


def _req() -> ContactRequest:
    return ContactRequest(name="Alice", email="alice@example.com",
                          phone="+15551234567", comment="Hello there.")


def _analysis() -> AIAnalysis:
    return AIAnalysis(sentiment="positive", category="sales", priority="high",
                      suggested_reply="Thanks!", ai_available=True)


@pytest.mark.asyncio
async def test_owner_and_user_messages_sent():
    sent = []

    async def fake_sender(message):
        sent.append(message)

    svc = EmailService(
        Settings(smtp_host="h", smtp_user="u", smtp_password="p", owner_email="owner@x.com"),
        sender=fake_sender,
    )
    await svc.send_owner(_req(), _analysis())
    await svc.send_user_copy(_req())

    assert len(sent) == 2
    assert sent[0]["To"] == "owner@x.com"
    assert sent[1]["To"] == "alice@example.com"


@pytest.mark.asyncio
async def test_unconfigured_email_is_noop():
    called = False

    async def fake_sender(message):
        nonlocal called
        called = True

    svc = EmailService(Settings(smtp_host=None), sender=fake_sender)
    await svc.send_owner(_req(), _analysis())
    assert called is False
