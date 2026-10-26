"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Draft Routes
  POST /api/draft — Save form progress to server-side cache

  How it works:
    1. Frontend auto-saves every 1.5s on field changes (debounced)
    2. Draft is stored keyed by user email with 24h TTL
    3. Primary storage is localStorage (client-side)
    4. This endpoint is the server-side backup (Redis in prod)
    5. Non-critical: if this fails, localStorage still has the data

  The locustfile.py sends drafts with weight=5 (~29% of traffic)
  because users save progress on every step change.
═══════════════════════════════════════════════════════════════════
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import DraftSaveRequest, DraftSaveResponse
from app.store import draft_store, rate_limiter

router = APIRouter()


@router.post(
    "/draft",
    response_model=DraftSaveResponse,
    tags=["Draft"],
    summary="Save form draft to server cache",
)
async def save_draft(body: DraftSaveRequest, request: Request):
    """
    Save the current form state as a server-side draft.
    Keyed by the user's email so it can be restored on any device.
    
    This is fire-and-forget from the frontend — failures are non-critical
    because localStorage is the primary draft store.
    """
    # ── Rate limit check ──
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"draft:{client_ip}"):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "message": "Draft save rate limited"},
        )

    # ── Extract email as the draft key ──
    email = body.formData.email or "anonymous"
    draft_key = f"draft:{email}"

    # ── Store with TTL ──
    draft_store.set(
        key=draft_key,
        value=body.model_dump(),
        ttl=settings.DRAFT_TTL_SECONDS,
    )

    return DraftSaveResponse(ok=True, message="Draft saved")
