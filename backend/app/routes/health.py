"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Health Route
  GET /api/health
  
  Used by:
    - Load balancers (ALB health checks)
    - HealthCheckUser in locustfile.py
    - Docker HEALTHCHECK
    - UptimeRobot / CloudWatch monitoring
═══════════════════════════════════════════════════════════════════
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.models import HealthResponse
from app.store import submission_queue

router = APIRouter()

# Track when the server started (for uptime calculation)
_start_time = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Monitoring"],
    summary="Liveness health check",
)
async def health_check():
    """
    Returns server health status, current timestamp, and uptime.
    Always returns 200 — if this fails, the container is dead.
    """
    return HealthResponse(
        status="healthy",
        service="phoenix-api",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=round(time.time() - _start_time, 2),
    )
