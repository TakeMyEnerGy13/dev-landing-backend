import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.ai import AIAnalysis

_PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    comment: str = Field(min_length=5, max_length=2000)
    # Permissive: a non-empty value is accepted here and treated as spam in ContactService.
    honeypot: str | None = Field(default=None)

    @field_validator("name", "comment")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        v = v.strip()
        if not _PHONE_RE.match(v) or not any(c.isdigit() for c in v):
            raise ValueError("invalid phone number")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "name": "Alice Founder",
                "email": "alice@example.com",
                "phone": "+1 555 123 4567",
                "comment": "Loved your portfolio — can we discuss a paid project?",
            }]
        }
    }


class ContactResponse(BaseModel):
    success: bool
    message: str
    analysis: AIAnalysis
