FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend/src
WORKDIR /app
# Reuse the exact tested lock; no credentials are needed to build this image.
COPY backend/requirements-dev.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock \
    && useradd --create-home --uid 10001 app
COPY --chown=app:app backend/src /app/backend/src
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "story_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
