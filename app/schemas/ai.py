from typing import Literal

from pydantic import BaseModel

Sentiment = Literal["positive", "neutral", "negative"]
Category = Literal["sales", "support", "spam", "other"]
Priority = Literal["low", "normal", "high"]


class AIAnalysis(BaseModel):
    sentiment: Sentiment
    category: Category
    priority: Priority
    suggested_reply: str
    ai_available: bool = True
