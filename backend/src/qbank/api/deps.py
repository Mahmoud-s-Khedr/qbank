from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.db import get_db
from qbank.models import Role, User
from qbank.services.errors import Forbidden, Unauthorized
from qbank.services.scoping import get


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
        raise Unauthorized() from None


def require_role(*roles: Role) -> Callable[..., User]:
    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user

    return dependency


DB = Annotated[Session, Depends(get_db)]
Current = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(require_role(Role.admin))]
Writer = Annotated[User, Depends(require_role(Role.admin, Role.editor))]
