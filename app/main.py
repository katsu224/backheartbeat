from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, button, couple, gallery, media, trigger, websocket
from app.core.middleware import RequestLoggingMiddleware
from app.core.rate_limiter import limiter
from app.db.init_db import init_db
from app.services.fcm_service import init_firebase

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("heartbeat_starting")
    await init_db()
    init_firebase()
    logger.info("heartbeat_ready")
    yield
    logger.info("heartbeat_shutdown")


app = FastAPI(
    title="Heartbeat API",
    description="Backend for the Heartbeat couples app — Layer 1 MVP",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter


# --- Exception handlers ---

def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "RATE_LIMIT_EXCEEDED", "message": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "VALIDATION_ERROR", "detail": exc.errors()},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTP_ERROR", "message": exc.detail},
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # StarletteHTTPException already handled above; this only fires for unexpected errors
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "HTTP_ERROR", "message": exc.detail},
        )
    logger.error("unhandled_error", path=request.url.path, error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "Internal server error"},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Middleware stack (applied in reverse order: last added = outermost)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(couple.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(trigger.router, prefix="/api/v1")
app.include_router(button.router, prefix="/api/v1")
app.include_router(gallery.router, prefix="/api/v1")
app.include_router(websocket.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
