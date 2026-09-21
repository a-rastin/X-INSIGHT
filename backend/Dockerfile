FROM python:3.11.16-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --locked --no-dev --no-install-project
COPY src ./src
ENV PYTHONPATH=/app/src
CMD ["uv", "run", "uvicorn", "x_insight.app:app", "--host", "0.0.0.0", "--port", "8000"]
