# Use an official Python runtime as a parent image
FROM python:3.11.5-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies needed for some Python packages (e.g., MySQL driver, image processing, OCR)
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Expose the API port
EXPOSE 8000

# Start Gunicorn using the existing config
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app"]
