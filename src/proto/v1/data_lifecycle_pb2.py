"""Compatibility alias; implementation lives in marty_plugin.proto.v1."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("marty_plugin.proto.v1.data_lifecycle_pb2")
