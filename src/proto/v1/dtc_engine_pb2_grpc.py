"""Compatibility alias; implementation lives in marty_plugin.proto.v1."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("marty_plugin.proto.v1.dtc_engine_pb2_grpc")
