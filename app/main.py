from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router as api_router


app = FastAPI(title="API Memorial Descritivo")
app.include_router(api_router)
