from app.config import get_settings
from app.handlers.metrics_store import MetricsStore
from app.handlers.rate_limiter import RateLimiter
from app.services.ai_service import AIService
from app.services.contact_service import ContactService
from app.services.email_service import EmailService

_rate_limiter: RateLimiter | None = None
_metrics_store: MetricsStore | None = None
_ai_service: AIService | None = None
_email_service: EmailService | None = None
_contact_service: ContactService | None = None


def reset() -> None:
    """Rebuild all singletons (used by tests after changing settings)."""
    global _rate_limiter, _metrics_store, _ai_service, _email_service, _contact_service
    _rate_limiter = _metrics_store = _ai_service = _email_service = _contact_service = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        s = get_settings()
        _rate_limiter = RateLimiter(s.rate_limit_max, s.rate_limit_window_seconds)
    return _rate_limiter


def get_metrics_store() -> MetricsStore:
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore(f"{get_settings().data_dir}/metrics.json")
    return _metrics_store


def get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService(get_settings())
    return _ai_service


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService(get_settings())
    return _email_service


def get_contact_service() -> ContactService:
    global _contact_service
    if _contact_service is None:
        _contact_service = ContactService(get_ai_service(), get_email_service(), get_metrics_store())
    return _contact_service
