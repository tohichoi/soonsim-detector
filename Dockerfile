FROM python:3.12-slim

# Install system dependencies for OpenCV and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install project dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy source code and scripts
COPY src/ ./src/
COPY models/ ./models/
COPY config/config.example.toml ./config/config.example.toml

# Create records directory
RUN mkdir -p /app/records

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "-m", "src.main", "--no-dashboard"]
