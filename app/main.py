from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.config import AppSettings, get_settings

load_dotenv()


def create_app(settings: AppSettings | None = None) -> FastAPI:
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

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    app.include_router(api_router)
    return app


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.warning(f"[DEBUG-VALIDATION] {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def general_exception_handler(request: Request, exc: Exception):
    logging.warning(f"[DEBUG-EXCEPTION] {type(exc).__name__}: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app = create_app()
