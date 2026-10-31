from fastapi import APIRouter, Request, Response

from qbank.api.deps import DB, Current
from qbank.config import get_settings
from qbank.models import User
from qbank.schemas.auth import ChangePassword, Login
from qbank.schemas.users import UserOut
from qbank.security.ratelimit import login_limit
from qbank.services import auth

router = APIRouter(prefix="/api/v1/auth")


@router.post("/login", response_model=UserOut)
def login(data: Login, request: Request, response: Response, db: DB) -> User:
    login_limit(request, data.email)
    user = auth.authenticate(db, data.email, data.password)
    request.state.user_id = str(user.id)
    request.state.org_id = str(user.org_id)
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


@router.post("/change-password", status_code=204)
def change_password(data: ChangePassword, response: Response, db: DB, user: Current) -> None:
    auth.change_password(db, user, data.current_password, data.new_password)
    response.delete_cookie("qbank_session", path="/")
    response.delete_cookie("qbank_csrf", path="/")
