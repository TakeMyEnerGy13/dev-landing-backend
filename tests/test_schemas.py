import pytest
from pydantic import ValidationError

from app.schemas.contact import ContactRequest


def test_valid_contact_request():
    req = ContactRequest(
        name="  Alice  ", email="alice@example.com",
        phone="+1 555 123 4567", comment="I would like to discuss a project.",
    )
    assert req.name == "Alice"          # trimmed
    assert req.honeypot is None


@pytest.mark.parametrize("field,value", [
    ("name", "A"),                       # too short
    ("email", "not-an-email"),
    ("phone", "abc"),                    # no digits
    ("comment", "hi"),                   # too short
])
def test_invalid_fields_raise(field, value):
    data = {"name": "Alice", "email": "alice@example.com",
            "phone": "+15551234567", "comment": "A valid comment here."}
    data[field] = value
    with pytest.raises(ValidationError):
        ContactRequest(**data)
