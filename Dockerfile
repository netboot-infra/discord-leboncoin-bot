# Use the official Python base image
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/data \
    CHECK_INTERVAL=10

# Create a non-root user with UID 1000
RUN useradd -m -u 1000 appuser

# Set working directory inside the container
WORKDIR /app

# Copy requirements.txt first for efficient caching
COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY main.py .

# Declare a volume for persistent data
VOLUME ["/data"]

# Switch to non-root user
USER appuser

# Default command (can be overridden)
CMD ["python", "main.py"]
