# ~/dw_agent_project/py_backend/Dockerfile

FROM python:3.11-slim

# Install system dependencies for Arch compatibility
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p /app/data/brains /app/data/uploads /app/logs && \
    chmod -R 777 /app/data /app/logs

EXPOSE 11400

CMD ["python", "-u", "main.py"]