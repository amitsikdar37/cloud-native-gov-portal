"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Upload Routes
  POST /api/upload-url — Generate pre-signed S3 PUT URL

  How it works:
    1. Frontend requests a pre-signed URL for photo/signature upload
    2. Backend generates a unique S3 key and signs a PUT URL
    3. Frontend uploads directly to S3 (never touches our server)
    4. This keeps upload bandwidth off our API server

  In demo/dev mode (no AWS credentials):
    Returns a mock URL so the frontend falls back to local preview.
═══════════════════════════════════════════════════════════════════
"""

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import UploadURLRequest, UploadURLResponse
from app.store import rate_limiter

router = APIRouter()

# Try to create an S3 client; gracefully handle missing credentials
_s3_client = None
try:
    import boto3
    _s3_client = boto3.client("s3", region_name=settings.AWS_REGION)
except Exception:
    pass


@router.post(
    "/upload-url",
    response_model=UploadURLResponse,
    tags=["Upload"],
    summary="Get pre-signed S3 upload URL",
)
async def get_upload_url(body: UploadURLRequest, request: Request):
    """
    Generate a pre-signed PUT URL for direct-to-S3 file upload.
    The frontend uploads the file directly to S3 using this URL,
    keeping upload traffic off the API server.

    Falls back to a mock response if AWS credentials aren't configured.
    """
    # ── Rate limit check ──
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"upload:{client_ip}"):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "message": "Upload URL rate limited"},
        )

    # ── Generate unique file key ──
    extension = body.fileName.rsplit(".", 1)[-1] if "." in body.fileName else "jpg"
    file_key = f"uploads/{uuid.uuid4().hex}.{extension}"

    # ── Try real S3 pre-signed URL ──
    if _s3_client and settings.S3_BUCKET != "phoenix-uploads":
        try:
            presigned_url = _s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.S3_BUCKET,
                    "Key": file_key,
                    "ContentType": body.fileType,
                },
                ExpiresIn=settings.S3_UPLOAD_EXPIRY,
            )
            return UploadURLResponse(
                ok=True,
                uploadUrl=presigned_url,
                fileKey=file_key,
            )
        except Exception:
            pass  # Fall through to mock

    # ── Mock response (dev/demo mode) ──
    # Frontend detects null/mock URL and simulates upload locally
    mock_url = f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{file_key}"
    return UploadURLResponse(
        ok=True,
        uploadUrl=mock_url,
        fileKey=file_key,
    )
