"""Protocol buffer re-exports.

All proto modules live in marty_plugin.proto.v1.
This package re-exports them so that ``from src.proto.v1 import …`` still
works in tests.
"""

from marty_plugin.proto.v1 import (  # noqa: F401
    biometric_service_pb2,
    biometric_service_pb2_grpc,
    cmc_engine_pb2,
    cmc_engine_pb2_grpc,
    common_services_pb2,
    common_services_pb2_grpc,
    csca_service_pb2,
    csca_service_pb2_grpc,
    data_lifecycle_pb2,
    data_lifecycle_pb2_grpc,
    document_signer_pb2,
    document_signer_pb2_grpc,
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
    pkd_service_pb2,
    pkd_service_pb2_grpc,
    rfid_service_pb2,
    rfid_service_pb2_grpc,
    storage_policy_pb2,
    storage_policy_pb2_grpc,
    td2_service_pb2,
    td2_service_pb2_grpc,
    trust_anchor_pb2,
    trust_anchor_pb2_grpc,
    visa_service_pb2,
    visa_service_pb2_grpc,
)
from . import biometric_service_pb2_grpc
from . import cmc_engine_pb2_grpc
from . import common_services_pb2_grpc
from . import csca_service_pb2_grpc
from . import data_lifecycle_pb2_grpc
from . import document_signer_pb2_grpc
from . import dtc_engine_pb2_grpc
from . import inspection_system_pb2_grpc
from . import mdl_engine_pb2_grpc
from . import mdoc_engine_pb2_grpc
from . import open_badges_service_pb2_grpc
from . import passport_engine_pb2_grpc
from . import pkd_service_pb2_grpc
from . import rfid_service_pb2_grpc
from . import storage_policy_pb2_grpc
from . import td2_service_pb2_grpc
from . import trust_anchor_pb2_grpc
from . import visa_service_pb2_grpc
