FROM registry.access.redhat.com/ubi9/python-310:latest

WORKDIR /app

# Install system dependencies if needed
RUN dnf install -y gcc python3-devel && \
    dnf clean all

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create config directory if it doesn't exist
RUN mkdir -p /app/config

# Expose port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=run.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run with gunicorn and eventlet worker for Socket.IO support
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "run:app"]
