"""Exercise public protobuf imports, wire data and generated RPC registration."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("first", ["marty_plugin.proto.v1", "proto.v1", "src.proto.v1"])
def test_public_namespaces_share_messages_and_rpc_bindings(first):
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    subprocess.run([sys.executable, "-c", '''
import importlib
import pickle
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import grpc

first, root = __import__("sys").argv[1:]
namespaces = [first] + [n for n in ("marty_plugin.proto.v1", "proto.v1", "src.proto.v1") if n != first]
for file in sorted((Path(root) / "src/marty_plugin/proto/v1").glob("*_pb2*.py")):
    modules = [importlib.import_module(n + "." + file.stem) for n in namespaces]
    assert all(m is modules[0] for m in modules), file.stem

pb = importlib.import_module(first + ".dtc_engine_pb2")
rpc = importlib.import_module(first + ".dtc_engine_pb2_grpc")
for index in (1, 2, 3):
    request = pb.CreateDTCRequest(passport_number="example", dtc_type=getattr(pb, "TYPE" + str(index)))
    getattr(request, "type" + str(index) + "_profile").SetInParent()
    wire = request.SerializeToString()
    for namespace in namespaces:
        owner = importlib.import_module(namespace + ".dtc_engine_pb2")
        decoded = owner.CreateDTCRequest.FromString(wire)
        assert decoded == request
        assert pickle.loads(pickle.dumps(decoded)) == request
        assert decoded.HasField("type" + str(index) + "_profile")
assert pb.CreateDTCRequest.DESCRIPTOR.fields_by_name["type1_profile"].number == 13
assert pb.CreateDTCRequest.DESCRIPTOR.fields_by_name["type2_profile"].number == 14
assert pb.CreateDTCRequest.DESCRIPTOR.fields_by_name["type3_profile"].number == 15

class Service(rpc.DTCEngineServicer):
    def GetDTC(self, request, context):
        return pb.DTCResponse(dtc_id=request.dtc_id, passport_number="example")

server = grpc.server(ThreadPoolExecutor(max_workers=1))
rpc.add_DTCEngineServicer_to_server(Service(), server)
port = server.add_insecure_port("127.0.0.1:0")
server.start()
try:
    with grpc.insecure_channel("127.0.0.1:" + str(port)) as channel:
        stub = importlib.import_module("proto.v1.dtc_engine_pb2_grpc").DTCEngineStub(channel)
        result = stub.GetDTC(pb.GetDTCRequest(dtc_id="roundtrip"), timeout=5)
        assert result.dtc_id == "roundtrip"
        assert result.passport_number == "example"
finally:
    server.stop(0).wait()
''', first, str(root)], check=True, env=env, cwd=root, timeout=30)
