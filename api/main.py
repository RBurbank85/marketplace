import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api import deps
from api.deps import get_api_key, rate_limiter
from config.settings import settings

from api.routers import (
    listings,
    opportunities,
    queue,
    collectors,
    categories,
    searches,
    analytics,
    scheduler,
    config,
)
from database.database import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    service = deps.get_scheduler_service()
    app.state.scheduler_service = service
    if settings.scheduler_autostart:
        service.start()
    try:
        yield
    finally:
        if settings.scheduler_autostart:
            service.stop()


app = FastAPI(
    title="MAIE API",
    description="Marketplace Arbitrage Intelligence Engine Backend API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(get_api_key), Depends(rate_limiter)],
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Log request details and add timing header."""
    start_time = time.time()
    request_id = request.headers.get("X-Request-ID")
    if not request_id or len(request_id) > 128:
        request_id = str(uuid4())
    request.state.request_id = request_id

    # Avoid logging sensitive information
    # We log the method and URL, but not headers (which might contain API keys)
    # or the body (which might contain secrets) unless specifically needed.
    method = request.method
    url = request.url.path

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id

    logging.info(
        f"{method} {url} - Status: {response.status_code} - Duration: {process_time:.4f}s"
    )

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Centralized exception handler to avoid leaking internal details."""
    logging.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {"code": "internal_server_error", "message": "An internal server error occurred."},
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return stable, secret-safe errors without exposing implementation details."""
    if isinstance(exc.detail, dict):
        detail = exc.detail
    else:
        code_by_status = {
            401: "authentication_required",
            403: "authentication_failed",
            404: "not_found",
            409: "conflict",
            422: "invalid_request",
            429: "rate_limited",
            503: "service_unavailable",
        }
        detail = {"code": code_by_status.get(exc.status_code, "request_failed"), "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "request_id": request.state.request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": {"code": "invalid_request", "message": "Request validation failed."},
            "request_id": request.state.request_id,
        },
    )


app.include_router(listings.router)
app.include_router(opportunities.router)
app.include_router(queue.router)
app.include_router(collectors.router)
app.include_router(categories.router)
app.include_router(searches.router)
app.include_router(analytics.router)
app.include_router(scheduler.router)
app.include_router(config.router)

_DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
app.mount(
    "/dashboard/assets",
    StaticFiles(directory=_DASHBOARD_DIR),
    name="dashboard-assets",
)


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(_DASHBOARD_DIR / "index.html")


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard", status_code=307)
