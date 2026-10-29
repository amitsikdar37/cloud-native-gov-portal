# ═══════════════════════════════════════════════════════════
#  Project Phoenix — Background Worker Dockerfile
#  Stateless, Least-Privilege Non-Root Consumer
# ═══════════════════════════════════════════════════════════

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -r appgroup && useradd -r -g appgroup -d /app appuser

COPY --chown=appuser:appgroup . .

USER appuser

CMD ["python", "main.py"]