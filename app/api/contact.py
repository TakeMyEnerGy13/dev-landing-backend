from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.dependencies import get_contact_service, get_rate_limiter
from app.handlers.rate_limiter import RateLimiter
from app.schemas.contact import ContactRequest, ContactResponse
from app.services.contact_service import ContactService

router = APIRouter(prefix="/api", tags=["contact"])


@router.post(
    "/contact",
    response_model=ContactResponse,
    summary="Submit the contact form",
    description="Validates input, runs AI triage, schedules email notifications "
                "(owner + user copy) in the background, and returns the AI analysis.",
    responses={
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def submit_contact(
    payload: ContactRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    limiter: RateLimiter = Depends(get_rate_limiter),
    service: ContactService = Depends(get_contact_service),
) -> ContactResponse:
    client_ip = request.client.host if request.client else "-"
    await limiter.check(client_ip)
    analysis = await service.handle(payload, schedule=background_tasks.add_task)
    return ContactResponse(
        success=True,
        message="Thanks! Your message was received.",
        analysis=analysis,
    )
