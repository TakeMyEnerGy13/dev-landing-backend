import json
from typing import Literal

from pydantic import BaseModel

from app.config import Settings
from app.core.logging import get_app_logger
from app.schemas.ai import AIAnalysis

SYSTEM_PROMPT = (
    "You are an assistant that triages inbound messages from a developer's "
    "landing page contact form. Analyze the user's message and return the "
    "sentiment, the request category, a priority, and a short, polite draft "
    "reply in the same language as the message. Do not invent facts about the "
    "site owner. Keep the draft reply under 80 words."
)


class AIAnalysisOut(BaseModel):
    """Structured-output schema sent to Gemini as `response_schema`.

    Intentionally has no default values: the Gemini API rejects response
    schemas with default field values (googleapis/python-genai#699). The
    `ai_available` flag lives on `AIAnalysis`, not here.
    """

    sentiment: Literal["positive", "neutral", "negative"]
    category: Literal["sales", "support", "spam", "other"]
    priority: Literal["low", "normal", "high"]
    suggested_reply: str


_HIGH_PRIORITY = ("urgent", "asap", "срочно", "немедленно")
_SALES = ("project", "hire", "job", "collaborat", "vacancy", "проект", "сотруднич", "ваканс")
_NEGATIVE = ("bad", "terrible", "awful", "broken", "disappoint", "плохо", "ужас")


def rule_based_fallback(comment: str) -> AIAnalysis:
    text = comment.lower()
    priority = "high" if any(k in text for k in _HIGH_PRIORITY) else "normal"
    category = "sales" if any(k in text for k in _SALES) else "other"
    sentiment = "negative" if any(k in text for k in _NEGATIVE) else "neutral"
    return AIAnalysis(
        sentiment=sentiment,
        category=category,
        priority=priority,
        suggested_reply="Thank you for reaching out — I will review your message and get back to you shortly.",
        ai_available=False,
    )


class AIService:
    def __init__(self, settings: Settings, client=None):
        self._settings = settings
        self._client = client
        if self._client is None and settings.ai_configured:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(settings.ai_timeout_seconds * 1000)),
            )

    async def analyze(self, comment: str) -> AIAnalysis:
        if self._client is None:
            return rule_based_fallback(comment)
        try:
            from google.genai import types

            resp = await self._client.aio.models.generate_content(
                model=self._settings.ai_model,
                contents=comment,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=AIAnalysisOut,
                ),
            )
            data = json.loads(resp.text)
            return AIAnalysis(**data, ai_available=True)
        except Exception as exc:  # noqa: BLE001 — any failure must degrade gracefully
            get_app_logger().warning(
                "", extra={"event": {"kind": "ai_fallback", "type": type(exc).__name__, "detail": str(exc)}}
            )
            return rule_based_fallback(comment)
