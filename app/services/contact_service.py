from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest


class ContactService:
    def __init__(self, ai, email, metrics):
        self._ai = ai
        self._email = email
        self._metrics = metrics

    async def handle(self, data: ContactRequest, schedule) -> AIAnalysis:
        if data.honeypot:
            return AIAnalysis(
                sentiment="neutral", category="spam", priority="low",
                suggested_reply="", ai_available=False,
            )

        analysis = await self._ai.analyze(data.comment)
        schedule(self._email.send_owner, data, analysis)
        schedule(self._email.send_user_copy, data)
        await self._metrics.increment(analysis.category, analysis.sentiment)
        return analysis
