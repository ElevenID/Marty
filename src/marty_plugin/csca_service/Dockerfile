# Dockerfile for csca-service
FROM python:3.10-slim

WORKDIR /app

COPY ../../pyproject.toml ../../uv.lock /app/

# Install UV and use it to install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv && \
    uv pip install --system -e .

# Create the proto directory structure
RUN mkdir -p /app/src/proto

# Copy the proto files
COPY ../../proto/ /app/proto/

# Copy the source code
COPY ../../src/ /app/src/

# Make directories Python packages
RUN touch /app/proto/__init__.py
RUN touch /app/src/__init__.py
RUN touch /app/src/proto/__init__.py

# Generate Python code from proto files directly into src/proto/
RUN cd /app && python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src/proto \
    --grpc_python_out=./src/proto \
    ./proto/*.proto

# Create data directories
RUN mkdir -p /app/data

# Command to run when container starts
ENV SERVICE_NAME=csca-service
ENV GRPC_PORT=8081
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.apps.csca_service"]
