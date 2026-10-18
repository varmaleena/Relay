FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY packages ./packages
COPY agents ./agents
COPY services ./services
USER 65532:65532
CMD ["sh", "-c", "exec python -m uvicorn services.a2a_receiver.http:create_receiver_app --factory --host 0.0.0.0 --port ${PORT} --no-access-log"]
