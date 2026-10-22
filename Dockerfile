# ==============================================================================
# SpaceV Control Plane & Ledger API Container
# Multi-stage production Dockerfile
# ==============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY spacev/ ./spacev/
COPY seeds/ ./seeds/
COPY reports/ ./reports/
COPY logs/ ./logs/
COPY tests/ ./tests/
COPY .env.example ./

# Expose API port
EXPOSE 8080

# Run FastAPI via Uvicorn
CMD ["uvicorn", "spacev.control_plane.main:app", "--host", "0.0.0.0", "--port", "8080"]
