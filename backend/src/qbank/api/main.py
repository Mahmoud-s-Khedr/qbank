import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from importlib.metadata import version
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response

from qbank.api.middleware import csrf_middleware
from qbank.api.routers import (
    auth,
    exams,
    exports,
    health,
    llm,
    org,
    review,
    sources,
    taxonomy,
    users,
)
from qbank.config import get_settings
from qbank.services.errors import DomainError

logger = structlog.get_logger()


def problem(
    status: int, detail: str, code: str, extra: dict[str, object] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "detail": detail,
            "code": code,
            **(extra or {}),
        },
    )


def create_app() -> FastAPI:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="Qbank", version=version("qbank"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        auth.router,
        exams.router,
        exports.router,
        health.router,
        llm.router,
        org.router,
        review.router,
        sources.router,
        taxonomy.router,
        users.router,
    ):
        app.include_router(router)
    app.middleware("http")(csrf_middleware)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # IDs are generated locally so untrusted headers cannot inject log content.
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return problem(exc.status, exc.code.replace("_", " "), exc.code, exc.extra)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return problem(exc.status_code, str(exc.detail["message"]), str(exc.detail["code"]))
        return problem(exc.status_code, str(exc.detail), "http_error")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(422, "Request validation failed", "validation_error")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", request_id=request.state.request_id)
        return problem(500, "Internal server error", "internal_error")

    return app


app = create_app()
