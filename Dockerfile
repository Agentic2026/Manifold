FROM python:3.14-slim AS api

WORKDIR /app
COPY api/ .

RUN pip install --no-cache-dir uv && \
    uv sync --locked --all-extras

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
