import json

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

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "category": {"type": "string", "enum": ["sales", "support", "spam", "other"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        "suggested_reply": {"type": "string"},
    },
    "required": ["sentiment", "category", "priority", "suggested_reply"],
    "additionalProperties": False,
}

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
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.ai_timeout_seconds,
            )

    async def analyze(self, comment: str) -> AIAnalysis:
        if self._client is None:
            return rule_based_fallback(comment)
        try:
            resp = await self._client.messages.create(
                model=self._settings.ai_model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": comment}],
                output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
            )
            text = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(text)
            return AIAnalysis(**data, ai_available=True)
        except Exception as exc:  # noqa: BLE001 — any failure must degrade gracefully
            get_app_logger().warning(
                "", extra={"event": {"kind": "ai_fallback", "type": type(exc).__name__, "detail": str(exc)}}
            )
            return rule_based_fallback(comment)
