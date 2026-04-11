FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi uvicorn aiohttp duckdb pandas tabulate
COPY src/LARS /app/src/LARS
COPY lars_service.py /app/lars_service.py
ENV PYTHONPATH=/app/src/LARS
ENV LARS_DUCKDB_PATH=/app/src/LARS/data/lars_data.duckdb
CMD ["uvicorn", "lars_service:app", "--host", "0.0.0.0", "--port", "8080"]
