# Dockerfile
FROM python:3.9-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ANYIO_BACKEND=asyncio
ENV AZURE_BLOB_CONNECTION_STRING=""
ENV KEYVAULT_NAME=MCChatAppKeyVault

# Set the working directory
WORKDIR /app

# Install system dependencies (including Git and PostgreSQL dev packages)
RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements.txt first for better caching
COPY requirements.txt .

# Install dependencies (including Gunicorn and Eventlet)
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

RUN pip uninstall -y trio trio-websocket || true


# Copy the rest of the application files
COPY . .

# Expose the port your app will run on (e.g., 3000)
EXPOSE 3000

# Run the app using Gunicorn with Eventlet for async and increased timeout
CMD ["gunicorn", \
     "--worker-class", "eventlet", \
     "-w", "1", \
     "-b", "0.0.0.0:3000", \
     "--timeout", "120", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "300", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "app:application"]
