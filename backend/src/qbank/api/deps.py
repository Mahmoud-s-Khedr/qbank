from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.db import get_db
from qbank.models import Role, User
from qbank.services.core import get


def error(status: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status, detail={"code": code, "message": code.replace("_", " ")}
    )


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    try:
        token = request.cookies["qbank_session"]
        claims = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "org", "role", "exp", "iat", "jti"]},
        )
        user = get(db, User, UUID(claims["org"]), UUID(claims["sub"]))
        if user is None or not user.is_active or user.role.value != claims["role"]:
            raise ValueError
        return user
    except (KeyError, ValueError, TypeError, jwt.InvalidTokenError):
        raise error(401, "unauthorized") from None


def require_role(*roles: Role) -> Callable[..., User]:
    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise error(403, "forbidden")
        return user

    return dependency
