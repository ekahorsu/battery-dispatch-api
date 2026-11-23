# Small production image for the dispatch API
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
# Cloud Run provides the PORT environment variable
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
