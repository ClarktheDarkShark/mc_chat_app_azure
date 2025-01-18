FROM python:3.9-slim

# Set environment variables for Python and Key Vault
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ANYIO_BACKEND=asyncio
ENV AZURE_BLOB_CONNECTION_STRING=""
ENV KEYVAULT_NAME=MCChatAppKeyVault2

# If your app expects a different variable for Key Vault, add it here:
# ENV AZURE_KEYVAULT_NAME=MCChatAppKeyVault

# Set the working directory
WORKDIR /app

# Install system dependencies (and clean up afterward)
RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    build-essential \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (required by some dependencies, e.g. orjson)
# We install Rust here and set the PATH so it is available for the pip install below.
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip uninstall -y trio trio-websocket || true

# Optionally, remove build dependencies (if not needed at runtime)
# Uncomment the following lines if you wish to remove build tools to reduce the image size.
# RUN apt-get purge -y git gcc build-essential curl && apt-get autoremove -y

# Copy the rest of the application code
COPY . .

# Copy SSL certificate and private key
# Ensure these files are in the same directory as your Dockerfile or update the paths accordingly.
COPY certificate.crt /etc/ssl/certs/
COPY private.key /etc/ssl/private/

# Overwrite the default NGINX configuration:
# Remove the pre-installed default config, copy your custom config, and create a symlink.
# Remove the pre-installed default config
RUN rm -f /etc/nginx/sites-enabled/default

# Copy your custom NGINX configuration
COPY nginx.conf /etc/nginx/sites-available/default

# Create a symlink in sites-enabled so NGINX will use your configuration
RUN ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default


# Expose ports for HTTP and HTTPS
# EXPOSE 80
# EXPOSE 443

# Copy Supervisor configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Start Supervisor to run NGINX and Gunicorn
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
