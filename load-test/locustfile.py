"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Locust Load Testing Script
  Member 3 Deliverable: Stress Test for 2,000 Concurrent Users
  
  Simulates real citizen behaviour:
    1. Send OTP → Verify OTP
    2. Save drafts across form steps
    3. Request S3 pre-signed upload URL
    4. Submit final application with X-Idempotency-Key
  
  Usage:
    pip install locust
    locust -f locustfile.py --host=http://localhost:3000
  
  Then open http://localhost:8089 in browser:
    → Users: 2000    → Spawn rate: 50/s
═══════════════════════════════════════════════════════════════════
"""

import uuid
import time
import random
import string
import json
from locust import HttpUser, task, between, events, tag


# ── Helpers ──
def random_email():
    name = ''.join(random.choices(string.ascii_lowercase, k=8))
    domain = random.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'gov.in'])
    return f"{name}@{domain}"


def random_phone():
    return '9' + ''.join(random.choices(string.digits, k=9))


def random_aadhaar():
    return ''.join(random.choices(string.digits, k=12))


def random_name():
    first = random.choice([
        'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun',
        'Ananya', 'Diya', 'Isha', 'Kavya', 'Priya',
        'Rohan', 'Sneha', 'Meera', 'Rahul', 'Sanya',
    ])
    last = random.choice([
        'Sharma', 'Patel', 'Singh', 'Kumar', 'Gupta',
        'Verma', 'Joshi', 'Reddy', 'Nair', 'Iyer',
    ])
    return f"{first} {last}"


def idempotency_key():
    return f"PHX-{uuid.uuid4().hex[:12]}"


# ══════════════════════════════════════════════════════
#  CitizenUser — Simulates a real applicant journey
# ══════════════════════════════════════════════════════
class CitizenUser(HttpUser):
    """
    Simulates a citizen going through the full application flow:
    OTP → Draft saves → Upload URL request → Final submit.
    
    Waits 1–3 seconds between actions (realistic typing/thinking time).
    """
    wait_time = between(1, 3)

    def on_start(self):
        """Generate unique identity for this simulated user."""
        self.user_email = random_email()
        self.user_phone = random_phone()
        self.user_name  = random_name()
        self.otp_verified = False

    # ── Task 1: OTP Send ──
    @task(3)
    @tag('otp')
    def send_otp(self):
        """POST /api/otp/send — Request a one-time password."""
        with self.client.post(
            "/api/otp/send",
            json={"email": self.user_email},
            headers={"Content-Type": "application/json"},
            name="/api/otp/send",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                resp.success()
            elif resp.status_code == 429:
                resp.success()  # Rate-limited is expected under load
            else:
                resp.failure(f"OTP send failed: {resp.status_code}")

    # ── Task 2: OTP Verify ──
    @task(2)
    @tag('otp')
    def verify_otp(self):
        """POST /api/otp/verify — Verify the OTP code."""
        with self.client.post(
            "/api/otp/verify",
            json={
                "email": self.user_email,
                "otp": "123456",  # Test OTP
            },
            headers={"Content-Type": "application/json"},
            name="/api/otp/verify",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                self.otp_verified = True
                resp.success()
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"OTP verify failed: {resp.status_code}")

    # ── Task 3: Save Draft (simulates multi-step form saves) ──
    @task(5)
    @tag('draft')
    def save_draft(self):
        """POST /api/draft — Save form progress to Redis."""
        draft_payload = {
            "formData": {
                "fullName": self.user_name,
                "email": self.user_email,
                "phone": self.user_phone,
                "dob": "1998-05-15",
                "gender": random.choice(["Male", "Female", "Other"]),
                "aadhaar": random_aadhaar(),
                "qualification": random.choice([
                    "10th", "12th", "Diploma", "Bachelors", "Masters"
                ]),
                "institution": random.choice([
                    "IIT Delhi", "NIT Trichy", "BITS Pilani",
                    "Anna University", "JNU", "Delhi University",
                ]),
                "yearOfPassing": str(random.randint(2018, 2026)),
                "percentage": f"{random.uniform(60, 98):.1f}%",
            },
            "currentStep": random.randint(1, 3),
            "savedAt": int(time.time() * 1000),
        }

        with self.client.post(
            "/api/draft",
            json=draft_payload,
            headers={"Content-Type": "application/json"},
            name="/api/draft",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                resp.success()
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"Draft save failed: {resp.status_code}")

    # ── Task 4: Request Upload URL ──
    @task(2)
    @tag('upload')
    def request_upload_url(self):
        """POST /api/upload-url — Get S3 pre-signed PUT URL."""
        with self.client.post(
            "/api/upload-url",
            json={
                "fileName": f"photo_{uuid.uuid4().hex[:8]}.jpg",
                "fileType": "image/jpeg",
            },
            headers={"Content-Type": "application/json"},
            name="/api/upload-url",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"Upload URL failed: {resp.status_code}")

    # ── Task 5: Final Form Submission (with Idempotency Key) ──
    @task(4)
    @tag('submit')
    def submit_application(self):
        """
        POST /api/submit — Submit final application.
        Includes X-Idempotency-Key header to test dedup logic.
        """
        idem_key = idempotency_key()

        payload = {
            "fullName": self.user_name,
            "email": self.user_email,
            "phone": self.user_phone,
            "dob": "1998-05-15",
            "gender": "Male",
            "aadhaar": random_aadhaar(),
            "qualification": "Bachelors",
            "institution": "IIT Delhi",
            "yearOfPassing": "2024",
            "percentage": "85.4%",
            "specialization": "Computer Science",
            "photoUrl": f"https://s3.amazonaws.com/phoenix-uploads/photo_{uuid.uuid4().hex[:8]}.jpg",
            "signatureUrl": f"https://s3.amazonaws.com/phoenix-uploads/sig_{uuid.uuid4().hex[:8]}.jpg",
            "submittedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        with self.client.post(
            "/api/submit",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Idempotency-Key": idem_key,
            },
            name="/api/submit",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                resp.success()
            elif resp.status_code == 429:
                # Rate-limited — acceptable under extreme load
                resp.success()
            elif resp.status_code == 409:
                # Idempotency conflict — expected for duplicate keys
                resp.success()
            else:
                resp.failure(f"Submit failed: {resp.status_code}")

    # ── Task 6: Duplicate Submit (tests idempotency protection) ──
    @task(1)
    @tag('submit', 'idempotency')
    def duplicate_submit(self):
        """
        Simulates the F5-stampede scenario: same user submitting 
        twice with the SAME idempotency key.
        The backend should return 200/202 from cache, not re-process.
        """
        idem_key = idempotency_key()

        payload = {
            "fullName": self.user_name,
            "email": self.user_email,
            "phone": self.user_phone,
            "dob": "1998-05-15",
            "gender": "Male",
            "aadhaar": random_aadhaar(),
            "qualification": "Bachelors",
            "institution": "IIT Delhi",
            "yearOfPassing": "2024",
            "percentage": "85.4%",
            "photoUrl": "https://s3.amazonaws.com/phoenix-uploads/test.jpg",
            "signatureUrl": "https://s3.amazonaws.com/phoenix-uploads/sig.jpg",
            "submittedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        headers = {
            "Content-Type": "application/json",
            "X-Idempotency-Key": idem_key,
        }

        # First submit
        with self.client.post(
            "/api/submit", json=payload, headers=headers,
            name="/api/submit [dup-1st]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202, 429):
                resp.success()
            else:
                resp.failure(f"Dup submit 1st failed: {resp.status_code}")

        # Immediate duplicate (same key)
        with self.client.post(
            "/api/submit", json=payload, headers=headers,
            name="/api/submit [dup-2nd]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202, 409, 429):
                resp.success()
            else:
                resp.failure(f"Dup submit 2nd failed: {resp.status_code}")


# ══════════════════════════════════════════════════════
#  HealthCheckUser — Lightweight monitor probe
# ══════════════════════════════════════════════════════
class HealthCheckUser(HttpUser):
    """
    Lightweight user that just pings the health endpoint.
    Useful for verifying uptime during the stress test.
    Weight is low so most load comes from CitizenUser.
    """
    weight = 1   # 1 HealthCheck per ~10 Citizens
    wait_time = between(5, 10)

    @task
    @tag('health')
    def health_check(self):
        """GET /api/health — Basic liveness check."""
        with self.client.get(
            "/api/health",
            name="/api/health",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Health check failed: {resp.status_code}")


# Assign weights: 10 citizens per 1 health checker
CitizenUser.weight = 10


# ── Event Hooks for Custom Reporting ──
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("╔══════════════════════════════════════════════╗")
    print("║   Project Phoenix — Stress Test Starting     ║")
    print("║   Target: 2,000 concurrent users             ║")
    print("║   Endpoints: OTP, Draft, Upload, Submit      ║")
    print("╚══════════════════════════════════════════════╝")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats
    total = stats.total
    print("\n╔══════════════════════════════════════════════╗")
    print("║   STRESS TEST COMPLETE — RESULTS SUMMARY     ║")
    print("╠══════════════════════════════════════════════╣")
    print(f"║  Total Requests:    {total.num_requests:>10,}              ║")
    print(f"║  Total Failures:    {total.num_failures:>10,}              ║")
    print(f"║  Avg Response (ms): {total.avg_response_time:>10.0f}              ║")
    print(f"║  95th %ile (ms):    {total.get_response_time_percentile(0.95) or 0:>10.0f}              ║")
    print(f"║  RPS (peak):        {total.total_rps:>10.1f}              ║")
    fail_pct = (total.num_failures / max(total.num_requests, 1)) * 100
    status = "✓ PASS" if fail_pct < 1 else "✗ FAIL"
    print(f"║  Failure Rate:      {fail_pct:>9.2f}%   {status}       ║")
    print("╚══════════════════════════════════════════════╝")
