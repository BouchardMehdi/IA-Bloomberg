FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir httpx==0.28.1 pydantic==2.11.7
COPY backend/app/__init__.py app/__init__.py
COPY backend/app/semantic app/semantic
COPY backend/app/schemas/semantic_analysis.py app/schemas/semantic_analysis.py
COPY backend/app/worker app/worker
RUN useradd --uid 10001 --create-home worker
USER worker
CMD ["python", "-m", "app.worker.main"]
