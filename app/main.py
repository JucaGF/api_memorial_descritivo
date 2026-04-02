from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from app.api.routes import router as api_router


app = FastAPI(title="API Memorial Descritivo")
app.include_router(api_router)
