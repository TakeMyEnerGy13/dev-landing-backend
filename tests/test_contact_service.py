import pytest

from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest
from app.services.contact_service import ContactService


class FakeAI:
    async def analyze(self, comment):
        return AIAnalysis(sentiment="positive", category="sales", priority="high",
                          suggested_reply="ok", ai_available=True)


class FakeEmail:
    async def send_owner(self, data, analysis): ...
    async def send_user_copy(self, data): ...


class FakeMetrics:
    def __init__(self): self.calls = []
    async def increment(self, category, sentiment): self.calls.append((category, sentiment))


def _req(honeypot=None):
    return ContactRequest(name="Alice", email="a@x.com", phone="+15551234567",
                          comment="Let us talk.", honeypot=honeypot)


@pytest.mark.asyncio
async def test_happy_path_schedules_emails_and_metrics():
    scheduled = []
    metrics = FakeMetrics()
    svc = ContactService(FakeAI(), FakeEmail(), metrics)

    analysis = await svc.handle(_req(), schedule=lambda fn, *a: scheduled.append((fn, a)))

    assert analysis.ai_available is True
    assert len(scheduled) == 2                       # owner + user copy
    assert metrics.calls == [("sales", "positive")]


@pytest.mark.asyncio
async def test_honeypot_short_circuits():
    scheduled = []
    metrics = FakeMetrics()
    svc = ContactService(FakeAI(), FakeEmail(), metrics)

    analysis = await svc.handle(_req(honeypot="i-am-a-bot"),
                                schedule=lambda fn, *a: scheduled.append((fn, a)))

    assert analysis.category == "spam"
    assert scheduled == []
    assert metrics.calls == []
