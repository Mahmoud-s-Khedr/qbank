from fastapi import APIRouter, Response

from qbank.api.deps import DB, Current
from qbank.config import get_settings
from qbank.models import User
from qbank.schemas.auth import Login
from qbank.schemas.users import UserOut
from qbank.services import auth

router = APIRouter(prefix="/api/v1/auth")


@router.post("/login", response_model=UserOut)
def login(data: Login, response: Response, db: DB) -> User:
    user = auth.authenticate(db, data.email, data.password)
    session, csrf = auth.issue_cookie_data(user)
    response.set_cookie(
        "qbank_session",
        session,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "qbank_csrf",
        csrf,
        httponly=False,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie("qbank_session", path="/")
    response.delete_cookie("qbank_csrf", path="/")


@router.get("/me", response_model=UserOut)
def me(user: Current) -> User:
    return user
