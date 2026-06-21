import pytest

from app.config import Settings
from app.services.ai_service import AIService, rule_based_fallback


@pytest.mark.asyncio
async def test_fallback_used_when_no_api_key():
    svc = AIService(Settings(gemini_api_key=None))
    result = await svc.analyze("This is URGENT, please respond ASAP about a job.")
    assert result.ai_available is False
    assert result.priority == "high"          # keyword "urgent"/"asap"
    assert result.category == "sales"         # keyword "job"


@pytest.mark.asyncio
async def test_fallback_on_client_error():
    class _BoomModels:
        @staticmethod
        async def generate_content(**kwargs):
            raise RuntimeError("network down")

    class BoomClient:
        class aio:
            models = _BoomModels()

    svc = AIService(Settings(gemini_api_key="test-key"), client=BoomClient())
    result = await svc.analyze("Hello, nice site.")
    assert result.ai_available is False


def test_rule_based_neutral_default():
    result = rule_based_fallback("Just saying hi.")
    assert result.sentiment == "neutral"
    assert result.ai_available is False
