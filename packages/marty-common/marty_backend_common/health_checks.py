"""
Common health check utilities for Marty services.

This module provides reusable health check functions for database connections,
external services, and other dependencies commonly used across Marty microservices.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any

try:
    import asyncpg

    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

try:
    import grpc

    HAS_GRPC = True
except ImportError:
    HAS_GRPC = False

logger = logging.getLogger(__name__)


def check_database_connection(connection_string: str, timeout: float = 5.0) -> bool:
    """
    Check PostgreSQL database connectivity.

    Args:
        connection_string: PostgreSQL connection string
        timeout: Connection timeout in seconds

    Returns:
        True if database is reachable, False otherwise
    """
    if not HAS_ASYNCPG:
        logger.warning("asyncpg not available, skipping database health check")
        return True

    try:
        import asyncio

        async def _check_db() -> bool:
            try:
                conn = await asyncpg.connect(connection_string, timeout=timeout)
                # Simple query to verify connection
                result = await conn.fetchval("SELECT 1")
                await conn.close()
                return result == 1
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                return False

        # Run async check in sync context
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create new one
            return asyncio.run(_check_db())
        else:
            # Running in async context, create task
            future = asyncio.ensure_future(_check_db())
            return loop.run_until_complete(future)

    except Exception as e:
        logger.warning(f"Database health check error: {e}")
        return False


def check_grpc_service(host: str, port: int, timeout: float = 5.0) -> bool:
    """
    Check gRPC service connectivity.

    Args:
        host: Service hostname
        port: Service port
        timeout: Connection timeout in seconds

    Returns:
        True if service is reachable, False otherwise
    """
    if not HAS_GRPC:
        logger.warning("grpc not available, skipping gRPC health check")
        return True

    try:
        channel = grpc.insecure_channel(f"{host}:{port}")

        # Use gRPC health checking if available
        try:
            from grpc_health.v1 import health_pb2, health_pb2_grpc

            health_stub = health_pb2_grpc.HealthStub(channel)
            request = health_pb2.HealthCheckRequest()

            response = health_stub.Check(request, timeout=timeout)
            channel.close()

            return response.status == health_pb2.HealthCheckResponse.SERVING

        except ImportError:
            # Fallback to basic connectivity check
            try:
                grpc.channel_ready_future(channel).result(timeout=timeout)
                channel.close()
                return True
            except grpc.FutureTimeoutError:
                channel.close()
                return False

    except Exception as e:
        logger.warning(f"gRPC service health check failed for {host}:{port}: {e}")
        return False


def check_http_service(url: str, timeout: float = 5.0, expected_status: int = 200) -> bool:
    """
    Check HTTP service connectivity.

    Args:
        url: Service URL
        timeout: Request timeout in seconds
        expected_status: Expected HTTP status code

    Returns:
        True if service responds with expected status, False otherwise
    """
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            return response.status_code == expected_status

    except ImportError:
        # Fallback to urllib
        try:
            import urllib.request

            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.getcode() == expected_status

        except Exception as e:
            logger.warning(f"HTTP service health check failed for {url}: {e}")
            return False

    except Exception as e:
        logger.warning(f"HTTP service health check failed for {url}: {e}")
        return False


def check_tcp_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """
    Check TCP port connectivity.

    Args:
        host: Target hostname
        port: Target port
        timeout: Connection timeout in seconds

    Returns:
        True if port is reachable, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        result = sock.connect_ex((host, port))
        sock.close()

        return result == 0

    except Exception as e:
        logger.warning(f"TCP port health check failed for {host}:{port}: {e}")
        return False


def check_file_system(path: str, min_free_mb: int = 100) -> bool:
    """
    Check file system health and available space.

    Args:
        path: File system path to check
        min_free_mb: Minimum free space in MB

    Returns:
        True if file system is healthy and has enough space, False otherwise
    """
    try:
        # Check if path exists
        import os
        import shutil

        if not os.path.exists(path):
            logger.warning(f"File system path does not exist: {path}")
            return False

        # Check available space
        total, used, free = shutil.disk_usage(path)
        free_mb = free // (1024 * 1024)

        if free_mb < min_free_mb:
            logger.warning(f"Insufficient disk space: {free_mb}MB < {min_free_mb}MB")
            return False

        return True

    except Exception as e:
        logger.warning(f"File system health check failed for {path}: {e}")
        return False


def check_memory_usage(max_usage_percent: float = 90.0) -> bool:
    """
    Check system memory usage.

    Args:
        max_usage_percent: Maximum acceptable memory usage percentage

    Returns:
        True if memory usage is below threshold, False otherwise
    """
    try:
        import psutil

        memory = psutil.virtual_memory()
        usage_percent = memory.percent

        if usage_percent > max_usage_percent:
            logger.warning(f"High memory usage: {usage_percent}% > {max_usage_percent}%")
            return False

        return True

    except ImportError:
        logger.warning("psutil not available, skipping memory health check")
        return True
    except Exception as e:
        logger.warning(f"Memory health check failed: {e}")
        return False


def check_cpu_usage(max_usage_percent: float = 90.0, interval: float = 1.0) -> bool:
    """
    Check system CPU usage.

    Args:
        max_usage_percent: Maximum acceptable CPU usage percentage
        interval: Measurement interval in seconds

    Returns:
        True if CPU usage is below threshold, False otherwise
    """
    try:
        import psutil

        usage_percent = psutil.cpu_percent(interval=interval)

        if usage_percent > max_usage_percent:
            logger.warning(f"High CPU usage: {usage_percent}% > {max_usage_percent}%")
            return False

        return True

    except ImportError:
        logger.warning("psutil not available, skipping CPU health check")
        return True
    except Exception as e:
        logger.warning(f"CPU health check failed: {e}")
        return False


def create_database_health_check(connection_string: str, timeout: float = 5.0) -> callable:
    """Create a database health check function."""

    def check() -> bool:
        return check_database_connection(connection_string, timeout)

    return check


def create_grpc_health_check(host: str, port: int, timeout: float = 5.0) -> callable:
    """Create a gRPC service health check function."""

    def check() -> bool:
        return check_grpc_service(host, port, timeout)

    return check


def create_http_health_check(
    url: str, timeout: float = 5.0, expected_status: int = 200
) -> callable:
    """Create an HTTP service health check function."""

    def check() -> bool:
        return check_http_service(url, timeout, expected_status)

    return check


def create_tcp_health_check(host: str, port: int, timeout: float = 5.0) -> callable:
    """Create a TCP port health check function."""

    def check() -> bool:
        return check_tcp_port(host, port, timeout)

    return check


def create_resource_health_check(
    max_memory_percent: float = 90.0,
    max_cpu_percent: float = 90.0,
    min_disk_mb: int = 100,
    disk_path: str = "/",
) -> callable:
    """Create a system resource health check function."""

    def check() -> bool:
        return (
            check_memory_usage(max_memory_percent)
            and check_cpu_usage(max_cpu_percent)
            and check_file_system(disk_path, min_disk_mb)
        )

    return check
