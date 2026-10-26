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

import json
import logging
import time
import uuid

import boto3
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import SubmitRequest, SubmitResponse
from app.store import idempotency_store, submission_queue, rate_limiter

router = APIRouter()
logger = logging.getLogger("phoenix.submit")

_sqs_client = None
_sqs_queue_url = None


def get_sqs():
    """Lazily initialize SQS client and queue URL."""
    global _sqs_client, _sqs_queue_url
    if _sqs_client is None:
        try:
            kwargs = {"region_name": settings.AWS_REGION}
            if settings.AWS_SQS_ENDPOINT:
                kwargs["endpoint_url"] = settings.AWS_SQS_ENDPOINT
            if settings.AWS_ACCESS_KEY_ID:
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            client = boto3.client("sqs", **kwargs)
            # Test connectivity / resolve queue URL
            q_url = settings.SQS_QUEUE_URL
            if not q_url:
                res = client.get_queue_url(QueueName=settings.SQS_QUEUE_NAME)
                q_url = res.get("QueueUrl")

            _sqs_client = client
            _sqs_queue_url = q_url
        except Exception as e:
            logger.warning("SQS client init failed (%s); using in-memory queue", e)
            _sqs_client = None
            _sqs_queue_url = None

    return _sqs_client, _sqs_queue_url


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

    # ── Enqueue for async processing (SQS -> PostgreSQL Worker) ──
    payload = {
        "referenceId": reference_id,
        "data": body.model_dump(),
        "idempotencyKey": x_idempotency_key or reference_id,
        "submittedAt": time.time(),
        "clientIp": client_ip,
    }

    enqueued_to_sqs = False
    sqs_client, q_url = get_sqs()
    if sqs_client and q_url:
        try:
            sqs_client.send_message(
                QueueUrl=q_url,
                MessageBody=json.dumps(payload),
            )
            enqueued_to_sqs = True
            logger.info("Enqueued submission %s to SQS at %s", reference_id, q_url)
        except Exception as e:
            logger.warning("Failed to push to SQS (%s); falling back to in-memory queue", e)

    if not enqueued_to_sqs:
        submission_queue.enqueue(payload)
        logger.info("Enqueued submission %s to in-memory queue", reference_id)

    # ── Return 202 Accepted (async pattern) ──
    return JSONResponse(
        status_code=202,
        content=response_data,
    )
