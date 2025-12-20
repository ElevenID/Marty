FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY marty-ui/src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MMF framework
COPY marty-microservices-framework/ /app/marty-microservices-framework/
ENV PYTHONPATH="${PYTHONPATH}:/app/marty-microservices-framework"

# Copy application code
COPY marty-ui/src/ /app/src/
COPY marty-ui/config/ /app/config/

# Set working directory to src
WORKDIR /app/src

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "oid4vc_api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
