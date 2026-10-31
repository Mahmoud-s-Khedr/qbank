from datetime import UTC, datetime
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.auth import create_token, hasher, verify_password
from qbank.models import User, normalize_email
from qbank.services.errors import Unauthorized
from qbank.services.unit_of_work import save

__all__ = ["hasher", "verify_password"]

# A fixed valid hash makes unknown-account attempts perform the same Argon2 work.
DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQxMjM0NTY3OA$"
    "2FtTn7Lvz1vu6R3VIMlFafYJWm+sWA+M5I0lH/44BXk"
)


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid or not user.is_active:
        raise Unauthorized("invalid_credentials")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
    user.last_login_at = datetime.now(UTC)
    save(db)
    return user


def issue_cookie_data(user: User) -> tuple[str, str]:
    return create_token(user), token_urlsafe(32)
