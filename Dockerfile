FROM python:3.12-slim

WORKDIR /app

# Install dependencies first, separately from app code, so Docker's layer
# cache skips this (slow) step on rebuilds where only code changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator/ ./orchestrator/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "orchestrator/server.py"]
