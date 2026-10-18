FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY packages ./packages
COPY agents ./agents
COPY services ./services
COPY packs ./packs
COPY docs/pack-sources ./docs/pack-sources
USER 65532:65532
CMD ["sh", "-c", "exec python -m uvicorn services.worker.http:create_worker_app --factory --host 0.0.0.0 --port ${PORT}"]
