from collections.abc import Awaitable, Callable
from secrets import compare_digest

from fastapi import Request
from starlette.responses import JSONResponse, Response


async def csrf_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path != "/api/v1/auth/login"
        and "qbank_session" in request.cookies
    ):
        csrf = request.cookies.get("qbank_csrf", "")
        header = request.headers.get("X-CSRF-Token", "")
        if not csrf or not header or not compare_digest(csrf.encode(), header.encode()):
            return JSONResponse(
                status_code=403,
                media_type="application/problem+json",
                content={
                    "type": "about:blank",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "CSRF validation failed",
                    "code": "csrf_failed",
                },
            )
    return await call_next(request)
