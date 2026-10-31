import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from qbank.models import Role
from qbank.schemas.auth import Login
from qbank.schemas.common import Output
from qbank.security.passwords import validate_password


class UserOut(Output):
    org_id: UUID
    email: str
    name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None


class UserCreate(Login):
    name: str
    role: Role

    _validate_password = field_validator("password")(validate_password)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()):
            raise ValueError("Invalid email address")
        return value


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
