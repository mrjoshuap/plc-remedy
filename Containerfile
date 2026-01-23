# PLC Self-Healing Middleware Container
# Based on RHEL9 UBI Python image
FROM registry.access.redhat.com/ubi9/python-310:latest

# Container metadata labels
LABEL maintainer="PLC Remediation Team"
LABEL description="PLC Self-Healing Middleware - Monitors Allen-Bradley PLCs and triggers automated remediation"
LABEL version="1.0"
LABEL org.opencontainers.image.title="PLC Self-Healing Middleware"
LABEL org.opencontainers.image.description="Flask-based middleware for PLC monitoring and automated remediation via Ansible Automation Platform"

# Set working directory
WORKDIR /app

# Install system dependencies
# gcc and python3-devel are needed for some Python packages that compile C extensions
RUN dnf install -y gcc python3-devel && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Create non-root user for security
# UBI images typically run as root by default, so we create a dedicated user
RUN useradd -r -u 1001 -g root -m -d /app -s /sbin/nologin -c "PLC Remediation App User" plcremedy && \
    chown -R plcremedy:root /app

# Copy requirements first for better layer caching
# This allows Docker to cache the pip install step if requirements.txt doesn't change
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create config directory with proper permissions
RUN mkdir -p /app/config && \
    chown -R plcremedy:root /app && \
    chmod -R g+w /app

# Switch to non-root user
USER plcremedy

# Expose port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=run.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Healthcheck to monitor container health
# Checks the /health endpoint every 30 seconds with 10 second timeout
# Container is considered unhealthy after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health').read()" || exit 1

# Run with gunicorn and eventlet worker for Socket.IO support
# Using 1 worker as recommended for eventlet with Socket.IO
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "run:app"]
