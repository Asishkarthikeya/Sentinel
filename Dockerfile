FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (e.g., for building some python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose ports for various services
EXPOSE 8000 8001 8002 8003 8501

# Default command (will be overridden by docker-compose)
CMD ["python", "app.py"]
