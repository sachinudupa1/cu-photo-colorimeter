FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY backend/requirements.txt /app/backend-requirements.txt
RUN pip install --no-cache-dir -r /app/backend-requirements.txt
COPY src /app/src
COPY backend/app /app/backend/app
ENV PYTHONPATH=/app/src:/app
CMD exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}
