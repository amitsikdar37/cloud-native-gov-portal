"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — OTP Routes
  POST /api/otp/send    — Generate and "send" a 6-digit OTP
  POST /api/otp/verify  — Validate the OTP code

  How it works:
    1. /send generates a random 6-digit code, stores it with 5-min TTL
    2. In production: triggers SES/SNS to email/SMS the code
    3. In dev/demo: always accepts "123456" as a valid code
    4. /verify checks the stored code and returns verified: true/false

  Rate-limited: prevents brute-force OTP guessing
═══════════════════════════════════════════════════════════════════
"""

import random

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import (
    OTPSendRequest,
    OTPSendResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
)
from app.store import otp_store, rate_limiter

router = APIRouter()


@router.post(
    "/otp/send",
    response_model=OTPSendResponse,
    tags=["OTP"],
    summary="Send OTP to email",
)
async def send_otp(body: OTPSendRequest, request: Request):
    """
    Generate a 6-digit OTP and store it keyed by email.
    In production, this would trigger AWS SES to email the code.
    In demo mode, the OTP is always 123456.
    """
    # ── Rate limit check ──
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"otp:send:{client_ip}"):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "message": "Too many OTP requests. Please wait."},
        )

    # ── Generate OTP ──
    otp_code = settings.OTP_TEST_CODE  # Demo mode: always 123456
    if settings.is_production:
        otp_code = "".join(str(random.randint(0, 9)) for _ in range(settings.OTP_LENGTH))

    # ── Store with TTL ──
    otp_store.set(
        key=f"otp:{body.email}",
        value=otp_code,
        ttl=settings.OTP_TTL_SECONDS,
    )

    # In production: send via SES/SNS here
    # ses_client.send_email(to=body.email, subject="Your OTP", body=f"Your code: {otp_code}")

    return OTPSendResponse(
        ok=True,
        message=f"OTP sent to {body.email}",
    )


@router.post(
    "/otp/verify",
    response_model=OTPVerifyResponse,
    tags=["OTP"],
    summary="Verify OTP code",
)
async def verify_otp(body: OTPVerifyRequest, request: Request):
    """
    Validate the OTP code against the stored value.
    The test code 123456 is always accepted in development mode.
    """
    # ── Rate limit check ──
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"otp:verify:{client_ip}"):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "message": "Too many verification attempts."},
        )

    # ── Check OTP ──
    stored_otp = otp_store.get(f"otp:{body.email}")

    # Accept the test code in non-production environments
    is_test_code = body.otp == settings.OTP_TEST_CODE and not settings.is_production
    is_valid = body.otp == stored_otp or is_test_code

    if not is_valid:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "verified": False, "message": "Invalid or expired OTP"},
        )

    # ── Invalidate used OTP (one-time use) ──
    otp_store.delete(f"otp:{body.email}")

    return OTPVerifyResponse(ok=True, verified=True)
