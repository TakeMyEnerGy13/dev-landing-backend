FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# data/ (logs + metrics) is created at runtime by the app; mount a volume to persist it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
