"""FastAPI application entry point."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import dashboard, datasets, forecasts, health, inventory, products
from app.config import get_settings
from app.errors import register_exception_handlers
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("stockwise.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_migrate:
        from app.db.migrate import upgrade_to_head

        upgrade_to_head(settings.database_url)
    logger.info("startup complete env=%s", settings.environment)
    yield


app = FastAPI(
    title="StockWise AI API",
    version=__version__,
    description=(
        "Demand forecasting and explainable inventory recommendations. "
        "All forecasts and metrics are computed from uploaded (or synthetic sample) data."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id, request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


register_exception_handlers(app)

app.include_router(health.router)
api_v1 = APIRouter(prefix="/api/v1")
for module in (products, datasets, forecasts, inventory, dashboard):
    api_v1.include_router(module.router)
app.include_router(api_v1)
