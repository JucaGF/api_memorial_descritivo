from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.api.routes import router as api_router


app = FastAPI(title="API Memorial Descritivo")

_default_cors_origins = "http://localhost:5173,http://127.0.0.1:5173"
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _default_cors_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.warning(f"[DEBUG-VALIDATION] {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logging.warning(f"[DEBUG-EXCEPTION] {type(exc).__name__}: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})

app.include_router(api_router)
