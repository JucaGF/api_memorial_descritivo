from __future__ import annotations

import logging
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.api.errors import (
    REQUEST_ID_HEADER,
    VALIDATION_ERROR_MESSAGE,
    build_error_response,
    format_sanitized_exception_trace,
    get_request_id,
)
from app.api.routes import router as api_router
from app.config import AppSettings, get_settings

load_dotenv()
logger = logging.getLogger(__name__)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    configure_logging()
    runtime_settings = settings or get_settings()
    app = FastAPI(title="API Memorial Descritivo")
    app.state.settings = runtime_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    app.include_router(api_router)
    return app


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed method=%s path=%s request_id=%s errors=%s",
        request.method,
        request.url.path,
        get_request_id(request),
        len(exc.errors()),
    )
    return build_error_response(
        status_code=422,
        code="validation_error",
        message=VALIDATION_ERROR_MESSAGE,
        request_id=get_request_id(request),
        details=exc.errors(),
        detail=exc.errors(),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "HTTP error method=%s path=%s request_id=%s status=%s",
        request.method,
        request.url.path,
        get_request_id(request),
        exc.status_code,
    )
    return build_error_response(
        status_code=exc.status_code,
        code="http_error",
        message=str(exc.detail),
        request_id=get_request_id(request),
    )


async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception method=%s path=%s request_id=%s error_type=%s\n%s",
        request.method,
        request.url.path,
        get_request_id(request),
        type(exc).__name__,
        format_sanitized_exception_trace(exc),
    )
    return build_error_response(
        status_code=500,
        code="internal_server_error",
        message="Erro interno ao processar a requisição.",
        request_id=get_request_id(request),
    )


app = create_app()
