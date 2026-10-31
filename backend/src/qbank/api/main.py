import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from importlib.metadata import version
from typing import Annotated
from uuid import uuid4

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.responses import Response

from qbank.config import get_settings
from qbank.db import get_db

logger = structlog.get_logger()


class Health(BaseModel):
    status: str = "ok"
    version: str
    db: str


def problem(status: int, detail: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "detail": detail,
            "code": code,
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

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # IDs are generated locally so untrusted headers cannot inject log content.
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return problem(exc.status_code, str(exc.detail), "http_error")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(422, "Request validation failed", "validation_error")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", request_id=request.state.request_id)
        return problem(500, "Internal server error", "internal_error")

    @app.get("/api/v1/health")
    def health(db: Annotated[Session, Depends(get_db)]) -> Health:
        try:
            db.execute(text("SET LOCAL statement_timeout = '2s'"))
            db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return Health(version=version("qbank"), db="down")
        return Health(version=version("qbank"), db="ok")

    return app


app = create_app()
