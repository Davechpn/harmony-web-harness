FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY harness/ harness/

CMD ["uvicorn", "harness.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
