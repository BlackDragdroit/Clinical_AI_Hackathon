FROM python:3.13-slim
RUN pip install --no-cache-dir uv==0.5.11
WORKDIR /srv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev
COPY core ./core
COPY engine ./engine
COPY app ./app
COPY engine ./engine
COPY scenario ./scenario
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
