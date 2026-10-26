"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Submit Routes
  POST /api/submit — Final application submission

  This is the MOST CRITICAL endpoint. It handles:
  
  1. IDEMPOTENCY PROTECTION (X-Idempotency-Key header)
     - Citizens panic-click "Submit" or hit F5 during deadline rush
     - Same idempotency key = return cached response, no duplicate
     - locustfile.py specifically tests this with duplicate_submit()
  
  2. ASYNCHRONOUS PROCESSING (202 Accepted pattern)
     - Don't make citizens wait for heavy DB writes during peak load
     - Accept → Enqueue → Return reference ID immediately
     - Background worker processes the queue (SQS in production)
  
  3. REFERENCE ID GENERATION
     - Returns ERP-XXXXXX format reference code
     - Citizens see this in the success modal on the frontend
═══════════════════════════════════════════════════════════════════
"""

import time
import uuid

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import SubmitRequest, SubmitResponse
from app.store import idempotency_store, submission_queue, rate_limiter

router = APIRouter()


def generate_reference_id() -> str:
    """Generate a unique reference ID in ERP-XXXXXX format."""
    # Use timestamp + random to ensure uniqueness
    ts = int(time.time()) % 1000000
    rand = uuid.uuid4().int % 1000
    return f"ERP-{ts:06d}{rand:03d}"


@router.post(
    "/submit",
    tags=["Submit"],
    summary="Submit final application",
    status_code=202,
)
async def submit_application(
    body: SubmitRequest,
    request: Request,
    x_idempotency_key: str = Header(None, alias="X-Idempotency-Key"),
):
    """
    Accept a final application submission.
    
    Returns 202 Accepted immediately — the application is queued for
    async processing (SQS → PostgreSQL worker in production).
    
    Idempotency:
      If X-Idempotency-Key matches a previous submission, the cached
      response is returned without re-processing. This prevents
      duplicate records when citizens double-click or hit F5.
    """
    # ── Rate limit check ──
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"submit:{client_ip}"):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "message": "Submission rate limited. Please wait."},
        )

    # ══════════════════════════════════════════════════
    #  IDEMPOTENCY CHECK
    #  This is the key resilience feature Member 2 built.
    #  
    #  Flow:
    #    1. Check if this idempotency key was seen before
    #    2. If YES → return the cached response (no duplicate)
    #    3. If NO → process normally and cache the response
    # ══════════════════════════════════════════════════
    if x_idempotency_key:
        cached = idempotency_store.get(f"idem:{x_idempotency_key}")
        if cached is not None:
            # Return the same response — no duplicate processing
            return JSONResponse(
                status_code=200,
                content=cached,
            )

    # ── Generate reference ID ──
    reference_id = generate_reference_id()

    # ── Build the response ──
    response_data = SubmitResponse(
        ok=True,
        referenceId=reference_id,
        status="queued",
        message="Application received and queued for processing",
    ).model_dump()

    # ── Cache response for idempotency ──
    if x_idempotency_key:
        idempotency_store.set(
            key=f"idem:{x_idempotency_key}",
            value=response_data,
            ttl=settings.IDEMPOTENCY_TTL_SECONDS,
        )

    # ── Enqueue for async processing ──
    # In production: SQS.send_message(QueueUrl=..., MessageBody=...)
    # Here we use our in-memory queue
    submission_queue.enqueue({
        "referenceId": reference_id,
        "data": body.model_dump(),
        "idempotencyKey": x_idempotency_key,
        "submittedAt": time.time(),
        "clientIp": client_ip,
    })

    # ── Return 202 Accepted (async pattern) ──
    return JSONResponse(
        status_code=202,
        content=response_data,
    )
