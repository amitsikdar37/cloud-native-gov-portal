# Project Phoenix — SLA & Performance Metrics

## 1. Service Level Agreements (SLAs)

| Metric | Target | Measurement |
|---|---|---|
| **Availability** | 99.9% uptime | CloudWatch / UptimeRobot |
| **Response Time (P50)** | < 200 ms | Locust + ALB metrics |
| **Response Time (P95)** | < 500 ms | Locust percentile report |
| **Response Time (P99)** | < 1,000 ms | Locust percentile report |
| **Error Rate** | < 0.5% of total requests | Locust failure count |
| **Form Completion** | < 2 seconds E2E | Live demo screen-right |
| **Zero 5xx Errors** | 0 under 2,000 users | Locust final summary |

---

## 2. Time-To-Recovery (TTR) Targets

| Failure Scenario | Max TTR | Verification Method |
|---|---|---|
| Single API container crash | ≤ 30 seconds | `docker stop` + ECS auto-restart |
| Redis cache miss (cold start) | ≤ 50 ms | localStorage fallback + Redis re-populate |
| SQS consumer crash | ≤ 45 seconds | Worker restart + message re-delivery |
| Database connection spike | 0 (buffered by SQS) | SQS queue depth metric |

---

## 3. Load Test Configuration

```
Tool:       Locust (Python)
Users:      2,000 concurrent
Spawn Rate: 50 users/second (40s ramp-up)
Duration:   5 minutes sustained load
Endpoints:  /api/otp/send, /api/otp/verify, /api/draft,
            /api/upload-url, /api/submit
```

### Task Weight Distribution

| Task | Weight | % of Traffic | Rationale |
|---|---|---|---|
| Save Draft | 5 | ~29% | Users save progress on every step change |
| Submit Application | 4 | ~24% | Final submissions under deadline rush |
| Send OTP | 3 | ~18% | First-time and retry OTP requests |
| Verify OTP | 2 | ~12% | Successful OTP entries |
| Request Upload URL | 2 | ~12% | Photo + signature upload requests |
| Duplicate Submit | 1 | ~6% | F5-stampede idempotency test |

---

## 4. Key Metrics to Capture During Demo

### Screen Left (Locust Dashboard — http://localhost:8089)
- **RPS (Requests/sec)**: Should sustain 400+ RPS
- **Failure %**: Must remain at 0%
- **Response Time Chart**: P50 line stays green/flat
- **Active Users**: Ramp to 2,000 and hold

### Screen Right (Live Browser)
- Load the form → should render in < 500 ms
- Fill all 4 steps → localStorage saves instantly
- Upload a photo → progress bar completes < 3s
- Submit → 202 Accepted in < 1 second

### Self-Healing Demo (Terminal)
```bash
# Kill a running API container
docker stop phoenix-api-1

# Watch ECS/Docker auto-restart (< 30s)
# Locust dashboard should show zero spike in errors
# SQS buffered submissions = zero data loss
```

---

## 5. Success Criteria Checklist

- [ ] Locust reaches 2,000 concurrent users with 0% failure rate
- [ ] P95 response time stays under 500ms throughout the test
- [ ] Live form submission completes in < 1 second during active swarm
- [ ] Container kill + recovery completes in ≤ 30 seconds
- [ ] No duplicate database records (idempotency keys verified)
- [ ] All SQS-buffered submissions eventually written to PostgreSQL
