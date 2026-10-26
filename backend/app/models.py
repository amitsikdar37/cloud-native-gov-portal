"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Pydantic Models
  Request/Response schemas with automatic validation.
  
  These models are what make FastAPI special:
  - Invalid requests get rejected with clear error messages
  - Swagger /docs auto-generates from these schemas
  - No manual validation code needed
═══════════════════════════════════════════════════════════════════
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# ══════════════════════════════════════════════════
#  OTP Models
# ══════════════════════════════════════════════════

class OTPSendRequest(BaseModel):
    """POST /api/otp/send — Request body."""
    email: EmailStr


class OTPSendResponse(BaseModel):
    ok: bool = True
    message: str = "OTP sent successfully"


class OTPVerifyRequest(BaseModel):
    """POST /api/otp/verify — Request body."""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OTPVerifyResponse(BaseModel):
    ok: bool = True
    verified: bool = True


# ══════════════════════════════════════════════════
#  Draft Models
# ══════════════════════════════════════════════════

class DraftFormData(BaseModel):
    """The actual form fields the citizen has filled so far."""
    fullName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    aadhaar: Optional[str] = None
    qualification: Optional[str] = None
    institution: Optional[str] = None
    yearOfPassing: Optional[str] = None
    percentage: Optional[str] = None
    specialization: Optional[str] = None


class DraftSaveRequest(BaseModel):
    """POST /api/draft — Save form progress."""
    formData: DraftFormData
    currentStep: int = Field(..., ge=1, le=4)
    savedAt: Optional[int] = None  # Unix timestamp in ms from frontend


class DraftSaveResponse(BaseModel):
    ok: bool = True
    message: str = "Draft saved"


# ══════════════════════════════════════════════════
#  Upload Models
# ══════════════════════════════════════════════════

class UploadURLRequest(BaseModel):
    """POST /api/upload-url — Request a pre-signed S3 PUT URL."""
    fileName: str = Field(..., min_length=1)
    fileType: str = Field(..., pattern=r"^image/(jpeg|png)$")


class UploadURLResponse(BaseModel):
    ok: bool = True
    uploadUrl: str
    fileKey: str


# ══════════════════════════════════════════════════
#  Submit Models
# ══════════════════════════════════════════════════

class SubmitRequest(BaseModel):
    """POST /api/submit — Final application submission."""
    fullName: str = Field(..., min_length=2)
    email: str
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
    dob: str
    gender: str
    aadhaar: str
    qualification: str
    institution: str
    yearOfPassing: str
    percentage: str
    specialization: Optional[str] = None
    photoUrl: Optional[str] = None
    signatureUrl: Optional[str] = None
    submittedAt: Optional[str] = None


class SubmitResponse(BaseModel):
    ok: bool = True
    referenceId: str
    status: str = "queued"
    message: str = "Application received and queued for processing"


# ══════════════════════════════════════════════════
#  Health
# ══════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "phoenix-api"
    timestamp: str
    uptime_seconds: float
