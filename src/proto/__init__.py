"""Protocol buffer definitions for Marty services.

This module re-exports from marty_plugin.proto to avoid duplicate registration.
Tests import from src.proto, but the actual proto files live in marty_plugin.proto.
"""

# Re-export from marty_plugin.proto to avoid duplicate proto registration
from marty_plugin.proto.v1 import (
    biometric_service_pb2,
    biometric_service_pb2_grpc,
    cmc_engine_pb2,
    cmc_engine_pb2_grpc,
    common_services_pb2,
    common_services_pb2_grpc,
    csca_service_pb2,
    csca_service_pb2_grpc,
    dtc_engine_pb2,
    dtc_engine_pb2_grpc,
    inspection_system_pb2,
    inspection_system_pb2_grpc,
    mdl_engine_pb2,
    mdl_engine_pb2_grpc,
    mdoc_engine_pb2,
    mdoc_engine_pb2_grpc,
    open_badges_service_pb2,
    open_badges_service_pb2_grpc,
    passport_engine_pb2,
    passport_engine_pb2_grpc,
    rfid_service_pb2,
    rfid_service_pb2_grpc,
)

__all__ = [
    # Common services
    "common_services_pb2",
    "common_services_pb2_grpc",
    # Engine services
    "passport_engine_pb2",
    "passport_engine_pb2_grpc",
    "mdl_engine_pb2",
    "mdl_engine_pb2_grpc",
    "mdoc_engine_pb2",
    "mdoc_engine_pb2_grpc",
    "dtc_engine_pb2",
    "dtc_engine_pb2_grpc",
    "cmc_engine_pb2",
    "cmc_engine_pb2_grpc",
    # Supporting services
    "rfid_service_pb2",
    "rfid_service_pb2_grpc",
    "biometric_service_pb2",
    "biometric_service_pb2_grpc",
    "inspection_system_pb2",
    "inspection_system_pb2_grpc",
    "csca_service_pb2",
    "csca_service_pb2_grpc",
    "open_badges_service_pb2",
    "open_badges_service_pb2_grpc",
]
