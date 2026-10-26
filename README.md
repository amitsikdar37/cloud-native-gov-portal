# Project Phoenix — Cloud-Native Resilient Public Sector Portal

> **Target Objective:** A fault-tolerant, zero-downtime, auto-scaling multi-step application pipeline built to survive deadline-day traffic surges without UI freezes, session drops, or database connection exhaustion.

---

## 📁 Repository Directory Structure

```text
cloud-native-gov-portal/
├── backend/                  # REST API Service (Member 2 ownership)
│   ├── Dockerfile            # Multi-stage Docker build for the backend API
│   └── src/                  # Express / FastAPI source code (routes, controllers, middlewares)
│
├── frontend/                 # Client UI Application (Member 3 ownership)
│   ├── Dockerfile            # Container build for frontend local development / Nginx
│   └── src/                  # 4-step form UI (HTML/CSS/JS or React) with localStorage auto-save
│
├── worker/                   # Asynchronous SQS Queue Consumer (Member 2 ownership)
│   ├── Dockerfile            # Multi-stage Docker build for the worker service
│   └── src/                  # SQS polling worker script writing throttled batches to PostgreSQL
│
├── infra/                    # Cloud Infrastructure & DB Setup (Member 1 ownership)
│   └── scripts/
│       └── init.sql          # PostgreSQL database schema and initialization scripts
│
├── load-test/                # Stress & Chaos Testing (Member 3 ownership)
│   └── locustfile.py         # Python Locust script simulating 2,000+ concurrent applicants
│
├── .env.example              # Template for environment variables (ZERO hardcoded secrets)
├── .gitignore                # Git ignore rules for node_modules, .env, build artifacts
├── docker-compose.yml        # Local multi-container orchestrator (API, Redis, Postgres, Mock SQS)
└── README.md                 # Project architecture, directory guide, and team runbook
```

---

## 🔍 Detailed Component & File Breakdown

### 1. `backend/`
* **Owner:** Member 2 (Backend Core & Async Pipeline)
* **Purpose:** Stateless API handling dynamic business logic:
  * `/api/otp`: Generates and verifies OTPs (stored in Redis with a 5-minute TTL).
  * `/api/draft`: Sub-millisecond temporary form draft saving in Redis.
  * `/api/upload-url`: Generates S3 Pre-Signed PUT URLs for direct-to-cloud photo uploads.
  * `/api/submit`: Validates incoming submissions, checks `X-Idempotency-Key` in Redis to prevent double-submissions, and pushes final payloads to Amazon SQS.
* **Key Rule:** Backend servers **never** touch raw image bytes and **never** synchronously write final form submissions directly to the relational database.

### 2. `frontend/`
* **Owner:** Member 3 (Frontend Experience & Testing Lead)
* **Purpose:** Responsive 4-step citizen application portal (Personal Info, Academic, Photo, Review & Submit):
  * Caches progress in browser `localStorage` and syncs with Redis drafts on every step transition.
  * Directly uploads applicant photos to Amazon S3 using the Pre-Signed URL.
  * Implements submit button debouncing (disables button on click to stop panic-clicking).

### 3. `worker/`
* **Owner:** Member 2 (Backend Core & Async Pipeline)
* **Purpose:** Background queue consumer:
  * Polls messages asynchronously from Amazon SQS.
  * Buffers and throttles writes into PostgreSQL in safe batches, completely insulating the primary database from connection exhaustion.

### 4. `infra/`
* **Owner:** Member 1 (Infrastructure, DevOps & Security Lead)
* **Purpose:** Database schemas, migration files, and infrastructure provisioning configs:
  * `scripts/init.sql`: Sets up PostgreSQL tables, relational indexes, and constraints executed when the local container starts.
  * Future cloud provisioning scripts (Terraform / CloudFormation / ECS task definitions).

### 5. `load-test/`
* **Owner:** Member 3 (Testing Lead) & Member 1 (Chaos Lead)
* **Purpose:** Distributed performance & resilience testing:
  * `locustfile.py`: Simulates 2,000 concurrent students hammering OTP and submission endpoints during deadline rushes.
  * Used for proving SLA targets (>99.9% uptime, <500ms P95 latency) and measuring Time to Recovery (TTR).

### 6. Root Configuration Files
* **`docker-compose.yml` (Member 1):** Orchestrates the full local environment with one command: API, Redis cache, PostgreSQL database, worker, and Mock SQS.
* **`.env.example` (Member 1):** Standardized environment variable template ensuring zero secrets or AWS keys are committed to Git.
* **`.gitignore`:** Prevents sensitive `.env` files, bulky dependency directories (`node_modules`), and logs from polluting the repository.

---

## 👥 Team Responsibility Matrix

| Team Member | Role | Core Ownership | Deliverables |
|---|---|---|---|
| **Member 1** | **Infra, DevOps & Security Lead** | AWS VPC, Dockerization, ALB, Mock SQS, CloudWatch metrics, Container health | `docker-compose.yml`, Multi-stage `Dockerfile`s, AWS ECS/ALB setup, TTR calibration |
| **Member 2** | **Backend Core & Pipeline Lead** | Stateless REST APIs, Redis caching, S3 Pre-Signed URLs, SQS worker, Idempotency | Endpoints (`/otp`, `/draft`, `/upload-url`, `/submit`), SQS consumer worker |
| **Member 3** | **Frontend & Stress Test Lead** | 4-step form UI, client-side auto-save, direct S3 upload, Locust load test | Citizen portal UI, Locust test script simulating 2,000 users, PPT metrics |

---

## 🌿 Git Branching Strategy & Workflow

To prevent merge conflicts and ensure parallel execution:
* **`main`**: Protected branch. **No direct pushes.** Merges happen via pull requests only after local container testing passes.
* **`feature/infra`**: Active branch for Member 1 (DevOps/Docker/Infra).
* **`feature/backend`**: Active branch for Member 2 (APIs/Worker/Redis).
* **`feature/ui`**: Active branch for Member 3 (Frontend/Locust).

### Sprint Definition of Done (DoD)
A feature is only considered **Done** when:
1. It runs cleanly inside its Docker container without manual host interventions.
2. It uses zero hardcoded AWS keys or database passwords (all read from environment variables).
3. It passes health check pings in under 15ms.
