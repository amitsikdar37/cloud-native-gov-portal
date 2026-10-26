"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — FastAPI Application Entry Point
  
  This is the main file that wires everything together:
    1. Creates the FastAPI app with metadata (powers Swagger /docs)
    2. Configures CORS (so the frontend can talk to the API)
    3. Registers all route handlers under /api prefix
    4. Adds request logging middleware
  
  Run with:
    cd backend
    uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
  
  Then visit:
    http://localhost:3000/docs   → Interactive Swagger UI
    http://localhost:3000/redoc  → Alternative API docs
═══════════════════════════════════════════════════════════════════
"""

import time
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routes import health, otp, draft, upload, submit

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phoenix")

# ══════════════════════════════════════════════════
#  Create the FastAPI Application
# ══════════════════════════════════════════════════
app = FastAPI(
    title="Project Phoenix — Exam Registration API",
    description=(
        "Cloud-native, zero-downtime backend for the National Examination "
        "Registration Portal. Handles OTP verification, form drafts, "
        "S3 uploads, and idempotent application submissions."
    ),
    version="1.0.0",
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",     # ReDoc alternative
)

# ══════════════════════════════════════════════════
#  CORS Middleware
#  
#  Without this, the browser blocks frontend → API requests
#  because they're on different ports (5500 vs 3000).
# ══════════════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS + ["*"],  # Allow all in dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Idempotency-Key"],
)


# ══════════════════════════════════════════════════
#  Request Logging Middleware
#  
#  Logs every request with method, path, status, and duration.
#  Useful for debugging and correlating with Locust output.
# ══════════════════════════════════════════════════
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    # Don't spam logs with health checks
    if request.url.path != "/api/health":
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

    # Add timing header for debugging
    response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"
    return response


# ══════════════════════════════════════════════════
#  Register Route Handlers
#  
#  All routes are prefixed with /api to match:
#    - Frontend CONFIG.API_BASE = 'http://localhost:3000/api'
#    - Locust endpoints: /api/otp/send, /api/submit, etc.
# ══════════════════════════════════════════════════
app.include_router(health.router, prefix="/api", tags=["Monitoring"])
app.include_router(otp.router,    prefix="/api", tags=["OTP"])
app.include_router(draft.router,  prefix="/api", tags=["Draft"])
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(submit.router, prefix="/api", tags=["Submit"])


# ── Root redirect to docs ──
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to Swagger docs for convenience."""
    return JSONResponse(
        content={
            "service": "Project Phoenix API",
            "docs": "/docs",
            "health": "/api/health",
        }
    )


# ══════════════════════════════════════════════════
#  Startup / Shutdown Events
# ══════════════════════════════════════════════════
@app.on_event("startup")
async def startup():
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   Project Phoenix — API Server Starting      ║")
    logger.info("║   Port: %-5d                                ║", settings.PORT)
    logger.info("║   Env:  %-11s                          ║", settings.ENV)
    logger.info("║   Docs: http://localhost:%d/docs           ║", settings.PORT)
    logger.info("╚══════════════════════════════════════════════╝")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Phoenix API shutting down gracefully…")
