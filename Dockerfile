# Use an official Python image as the base
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install system dependencies (including Git and PostgreSQL dev packages)
RUN apt-get update && apt-get install -y git libpq-dev gcc build-essential

# Copy the application files
COPY . .

# Install dependencies (if requirements.txt exists)
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn and Gevent (explicit version)
RUN pip install gunicorn gevent==21.12.0

# Expose the port your app will run on (e.g., 3000)
EXPOSE 3000

# Run the app using Gunicorn with Gevent for async and increased timeout
CMD ["gunicorn", "-w", "2","-k", "gevent","-b", "0.0.0.0:3000", "--timeout", "120","--max-requests", "1000", "--max-requests-jitter", "300", "app:app"]


