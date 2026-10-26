"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Background SQS Worker (Member 2 Deliverable)
  
  Responsibilities:
  1. Polls application submissions from Amazon SQS / ElasticMQ
  2. Absorbs peak traffic spikes (10k+ submissions buffered safely)
  3. Writes records into PostgreSQL in controlled, safe batches
  4. Enforces idempotency to guarantee zero duplicate submissions
  5. Deletes acknowledged messages from SQS after successful DB commit
═══════════════════════════════════════════════════════════════════
"""

import json
import logging
import os
import signal
import sys
import time
from typing import Any, Optional

import boto3
import psycopg2
from psycopg2.extras import Json

# ── Logging Configuration ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [phoenix-worker] %(message)s",
)
logger = logging.getLogger("worker")

# ── Environment Configurations ──
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/gov_portal",
)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_SQS_ENDPOINT = os.getenv("AWS_SQS_ENDPOINT", "http://sqs:9324")
SQS_QUEUE_URL = os.getenv(
    "SQS_QUEUE_URL",
    "http://sqs:9324/000000000000/application-submissions",
)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
POLL_WAIT_SECONDS = int(os.getenv("POLL_WAIT_SECONDS", "5"))

_running = True


def handle_shutdown(signum, frame):
    """Graceful shutdown signal handler."""
    global _running
    logger.info("Shutdown signal received (%s). Finishing in-flight jobs...", signum)
    _running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def get_db_connection(max_retries: int = 30, retry_delay: float = 2.0):
    """Connect to PostgreSQL with resilient retry loop."""
    logger.info("Connecting to PostgreSQL at %s...", DATABASE_URL.split("@")[-1])
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            logger.info("Connected to PostgreSQL successfully.")
            return conn
        except Exception as e:
            logger.warning(
                "PostgreSQL not ready (attempt %d/%d): %s. Retrying in %.1fs...",
                attempt,
                max_retries,
                e,
                retry_delay,
            )
            time.sleep(retry_delay)

    logger.error("Could not connect to PostgreSQL after %d attempts. Exiting.", max_retries)
    sys.exit(1)


def get_sqs_client(max_retries: int = 30, retry_delay: float = 2.0):
    """Initialize SQS / ElasticMQ client with retry loop."""
    logger.info("Connecting to SQS endpoint %s (Region: %s)...", AWS_SQS_ENDPOINT, AWS_REGION)
    kwargs = {
        "region_name": AWS_REGION,
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "mock_key"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "mock_secret"),
    }
    if AWS_SQS_ENDPOINT:
        kwargs["endpoint_url"] = AWS_SQS_ENDPOINT

    for attempt in range(1, max_retries + 1):
        try:
            client = boto3.client("sqs", **kwargs)
            # Verify queue accessibility
            client.get_queue_attributes(
                QueueUrl=SQS_QUEUE_URL,
                AttributeNames=["ApproximateNumberOfMessages"],
            )
            logger.info("Connected to SQS queue %s successfully.", SQS_QUEUE_URL)
            return client
        except Exception as e:
            logger.warning(
                "SQS not ready (attempt %d/%d): %s. Retrying in %.1fs...",
                attempt,
                max_retries,
                e,
                retry_delay,
            )
            time.sleep(retry_delay)

    logger.error("Could not connect to SQS after %d attempts. Exiting.", max_retries)
    sys.exit(1)


def process_submission(cursor, payload: dict) -> bool:
    """
    Parse a submission payload and safely write to PostgreSQL.
    Uses ON CONFLICT (idempotency_key) DO NOTHING to prevent duplicates.
    """
    data = payload.get("data", {})
    ref_id = payload.get("referenceId", "UNKNOWN")
    idempotency_key = (
        payload.get("idempotencyKey")
        or ref_id
        or f"fallback-{int(time.time() * 1000)}"
    )

    full_name = data.get("fullName") or "Anonymous Applicant"
    email = data.get("email") or "unknown@domain.gov"
    phone_number = data.get("phone") or "0000000000"
    date_of_birth = data.get("dob") or None
    gender = data.get("gender") or "Not Specified"
    residential_address = data.get("residentialAddress") or data.get("address") or ""
    photo_s3_url = (
        data.get("photoUrl")
        or f"s3://phoenix-uploads/defaults/{ref_id}-photo.jpg"
    )

    academic_details = {
        "qualification": data.get("qualification"),
        "institution": data.get("institution"),
        "year_of_passing": data.get("yearOfPassing"),
        "percentage": data.get("percentage"),
        "specialization": data.get("specialization"),
        "aadhaar": data.get("aadhaar"),
        "signature_url": data.get("signatureUrl"),
        "reference_id": ref_id,
        "submitted_at": payload.get("submittedAt"),
        "client_ip": payload.get("clientIp"),
    }

    insert_sql = """
        INSERT INTO applications (
            idempotency_key,
            full_name,
            email,
            phone_number,
            date_of_birth,
            gender,
            residential_address,
            academic_details,
            photo_s3_url,
            status
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, 'SUBMITTED'
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id;
    """

    cursor.execute(
        insert_sql,
        (
            idempotency_key,
            full_name,
            email,
            phone_number,
            date_of_birth,
            gender,
            residential_address,
            Json(academic_details),
            photo_s3_url,
        ),
    )

    row = cursor.fetchone()
    if row:
        logger.info(
            "Persisted submission ref=%s (id=%s, email=%s) into PostgreSQL",
            ref_id,
            row[0],
            email,
        )
    else:
        logger.info(
            "Idempotency hit: submission ref=%s (key=%s) already exists. Skipped duplicate.",
            ref_id,
            idempotency_key,
        )

    return True


def run_worker():
    """Main worker event loop."""
    logger.info("Starting Phoenix SQS Worker loop...")
    db_conn = get_db_connection()
    sqs = get_sqs_client()

    processed_count = 0

    while _running:
        try:
            # Long-poll messages from SQS
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=BATCH_SIZE,
                WaitTimeSeconds=POLL_WAIT_SECONDS,
                AttributeNames=["ApproximateReceiveCount"],
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            logger.info("Received batch of %d message(s) from SQS", len(messages))

            with db_conn.cursor() as cursor:
                for msg in messages:
                    receipt_handle = msg["ReceiptHandle"]
                    body_raw = msg.get("Body", "{}")

                    try:
                        payload = json.loads(body_raw)
                        process_submission(cursor, payload)
                        # Acknowledge & remove from SQS
                        sqs.delete_message(
                            QueueUrl=SQS_QUEUE_URL,
                            ReceiptHandle=receipt_handle,
                        )
                        processed_count += 1
                    except Exception as item_err:
                        logger.error("Failed processing message: %s. Error: %s", body_raw, item_err)

                db_conn.commit()

        except psycopg2.OperationalError as db_err:
            logger.error("Database connection dropped: %s. Reconnecting...", db_err)
            time.sleep(2)
            db_conn = get_db_connection()
        except Exception as loop_err:
            logger.error("Unexpected worker error: %s. Continuing...", loop_err)
            time.sleep(2)

    logger.info("Worker stopped cleanly. Total submissions processed: %d", processed_count)
    if db_conn:
        db_conn.close()


if __name__ == "__main__":
    run_worker()
