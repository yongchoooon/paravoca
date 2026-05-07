from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_data,
    routes_data_sources,
    routes_health,
    routes_llm,
    routes_rag,
    routes_runs,
    routes_workflows,
)
from app.core.config import get_settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router, prefix="/api", tags=["health"])
app.include_router(routes_workflows.router, prefix="/api")
app.include_router(routes_runs.router, prefix="/api")
app.include_router(routes_data.router, prefix="/api")
app.include_router(routes_data_sources.router, prefix="/api")
app.include_router(routes_rag.router, prefix="/api")
app.include_router(routes_llm.router, prefix="/api")
