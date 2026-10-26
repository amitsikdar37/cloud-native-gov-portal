# ═══════════════════════════════════════════════════════════
#  Project Phoenix — Background Worker Dockerfile
#  Consumes SQS messages and safely batches writes to PostgreSQL
# ═══════════════════════════════════════════════════════════

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for cached layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Run the worker process
CMD ["python", "main.py"]
