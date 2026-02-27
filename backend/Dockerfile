FROM python:3.12-slim

# Install system dependencies if any, clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into .venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --frozen --no-cache

# Copy application source code
COPY . .

# Expose port
EXPOSE 8000

# Start app using uv to run from the virtual environment
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]