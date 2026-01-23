FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Prague
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install project dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure data directories exist
RUN mkdir -p logs data config site/config

# Runtime user
# RUN useradd -m appuser && chown -R appuser /app
# USER appuser

# Entry point
# Use -u for unbuffered output to see logs in docker logs
CMD ["python", "-u", "visa_status.py", "monitor", "-e", ".env"]
