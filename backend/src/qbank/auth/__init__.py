from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from qbank.config import get_settings
from qbank.models import User

hasher = PasswordHasher()


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user: User) -> str:
    now = datetime.now(UTC)
    settings = get_settings()
    return jwt.encode(
        {
            "sub": str(user.id),
            "org": str(user.org_id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(minutes=settings.session_ttl_minutes),
            "jti": str(uuid4()),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
