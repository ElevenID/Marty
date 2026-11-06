"""Exercise actual gRPC dispatch, trusted transport identity and request-scoped authorization."""

import asyncio
import importlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace

import grpc
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def modules():
    names = ("marty_common", "marty_plugin")
    previous = {k: v for k, v in sys.modules.items() if any(k == n or k.startswith(n + ".") for n in names)}
    for key in previous:
        del sys.modules[key]
    for name, path in (("marty_common", ROOT / "packages/marty-common/marty_common"),
                       ("marty_plugin", ROOT / "src/marty_plugin")):
        module = ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    try:
        yield importlib.import_module
    finally:
        for key in list(sys.modules):
            if any(key == n or key.startswith(n + ".") for n in names):
                del sys.modules[key]
        sys.modules.update(previous)


def transport_credentials():
    ca_key, ca = certificate_pair(name="test-ca", is_ca=True)
    server_key, server_cert = certificate_pair(ca_key, ca)
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    private = lambda key: key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption())
    server = grpc.ssl_server_credentials([(private(server_key), pem(server_cert))],
                                         root_certificates=pem(ca), require_client_auth=True)
    clients = {}
    for name in ("alice", "bob"):
        key, cert = certificate_pair(ca_key, ca, name)
        clients[name] = grpc.ssl_channel_credentials(pem(ca), private(key), pem(cert))
    return server, clients


@pytest.mark.parametrize("kind", ["unary_unary", "unary_stream", "stream_unary", "stream_stream"])
def test_real_rpc_shapes_scope_authorization_and_reject_forged_credentials(modules, kind):
    module = modules("marty_common.auth_interceptor")
    authorization = modules("marty_common.authorization")
    interceptor = module.AuthServerInterceptor()
    server_credentials, clients = transport_credentials()
    observed = []

    def evaluate(context):
        observed.append((context.identity, context.roles))
        return context.identity in clients and context.roles == []

    engine = SimpleNamespace(evaluate=evaluate)
    request_streaming, response_streaming = kind.startswith("stream_"), kind.endswith("_stream")

    @authorization.require("document:read", policy_engine=engine)
    async def authorized(request, context):
        await asyncio.sleep(0.01)
        identity = module.get_auth_context().identity
        values = [item async for item in request] if request_streaming else [request]
        assert module.get_auth_context().identity == identity
        return identity.encode() + b":" + b"".join(values)

    async def stream(request, context):
        result = await authorized(request, context)
        yield result
        await asyncio.sleep(0)
        assert module.get_auth_context().authenticated
        yield result

    async def run():
        server = grpc.aio.server(interceptors=[interceptor])
        handler = getattr(grpc, kind + "_rpc_method_handler")(stream if response_streaming else authorized)
        server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("probe", {"call": handler}),))
        port = server.add_secure_port("127.0.0.1:0", server_credentials)
        await server.start()
        try:
            async def invoke(identity):
                async with grpc.aio.secure_channel(f"localhost:{port}", clients[identity]) as channel:
                    call = getattr(channel, kind)("/probe/call")
                    response = call(iter([b"ok"]) if request_streaming else b"ok",
                                    metadata=(("x-client-cert-subject", "admin"),), timeout=5)
                    return [value async for value in response] if response_streaming else await response

            results = await asyncio.gather(invoke("alice"), invoke("bob"))
            expected = [b"alice:ok", b"bob:ok"]
            assert results == ([[value, value] for value in expected] if response_streaming else expected)
            async with grpc.aio.secure_channel(f"localhost:{port}", clients["alice"]) as channel:
                for metadata in ((("authorization", "Bearer forged"),),
                                 (("authorization", "Bearer alice"), ("authorization", "Bearer bob"))):
                    call = getattr(channel, kind)("/probe/call")
                    with pytest.raises(grpc.aio.AioRpcError) as error:
                        response = call(iter([b"ok"]) if request_streaming else b"ok", metadata=metadata, timeout=5)
                        if response_streaming:
                            [value async for value in response]
                        else:
                            await response
                    assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED
        finally:
            await server.stop(0)
        assert module.get_auth_context() is None

    asyncio.run(run())
    assert sorted(observed) == [("alice", []), ("bob", [])]
    with pytest.raises(authorization.AuthorizationError):
        asyncio.run(authorized(b"ok", SimpleNamespace(invocation_metadata=lambda: (("x-client-cert-subject", "alice"),))))


def certificate_pair(ca_key=None, ca_cert=None, name="localhost", *, is_ca=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_cert.subject if ca_cert else subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(ca_key or key, hashes.SHA256()))
    return key, cert


def test_real_mutual_tls_uses_certificate_identity_never_forwarded_headers(modules):
    module = modules("marty_common.auth_interceptor")
    ca_key, ca = certificate_pair(name="test-ca", is_ca=True)
    server_key, server_cert = certificate_pair(ca_key, ca)
    client_key, client_cert = certificate_pair(ca_key, ca, "client.test")
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    private = lambda key: key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption())

    async def run():
        async def behavior(request, context):
            auth = module.get_auth_context()
            assert auth.auth_method == "mtls" and not auth.claims.get("roles")
            return auth.identity.encode()

        server = grpc.aio.server(interceptors=[module.AuthServerInterceptor()])
        server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("probe", {
            "call": grpc.unary_unary_rpc_method_handler(behavior)}),))
        credentials = grpc.ssl_server_credentials([(private(server_key), pem(server_cert))],
                                                   root_certificates=pem(ca), require_client_auth=True)
        port = server.add_secure_port("127.0.0.1:0", credentials)
        await server.start()
        try:
            credentials = grpc.ssl_channel_credentials(pem(ca), private(client_key), pem(client_cert))
            async with grpc.aio.secure_channel(f"localhost:{port}", credentials) as channel:
                call = channel.unary_unary("/probe/call")
                assert await call(b"ok", metadata=(("x-client-cert-subject", "admin"),), timeout=5) == b"client.test"
                with pytest.raises(grpc.aio.AioRpcError) as error:
                    await call(b"ok", metadata=(("authorization", "Bearer forged"),), timeout=5)
                assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED
        finally:
            await server.stop(0)

    asyncio.run(run())


@pytest.mark.parametrize("setting", [
    {"jwt_public_key": "public-pem"}, {"jwt_jwks": {"keys": [{}]}},
    {"jwt_issuer": "https://issuer.test"}, {"jwt_audience": "grpc"},
    {"jwt_key_id": "key"}, {"jwt_algorithm": "ES256"},
])
def test_removed_jwt_configuration_fails_before_server_start(modules, setting):
    module = modules("marty_common.auth_interceptor")
    with pytest.raises(ValueError, match="JWT authentication is retired"):
        module.AuthServerInterceptor(**setting)


def test_health_bypass_is_exact_and_authentication_cannot_be_disabled(modules):
    module = modules("marty_common.auth_interceptor")
    interceptor = module.AuthServerInterceptor()
    assert interceptor._is_health_check(SimpleNamespace(method="/grpc.health.v1.Health/Check"))
    assert not interceptor._is_health_check(SimpleNamespace(method="/probe/healthAdmin"))
    for kwargs in ({"require_auth": False}, {"jwt_secret": "retired"}, {"jwt_algorithm": "HS256"},
                   {"jwt_jwks": {"keys": [{}]}}):
        with pytest.raises(ValueError):
            module.AuthServerInterceptor(**kwargs)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_handler_context_is_reset_after_exception_or_cancellation(modules, monkeypatch, streaming, failure):
    module = modules("marty_common.auth_interceptor")
    interceptor = module.AuthServerInterceptor()

    async def behavior(request, context):
        assert module.get_auth_context().identity == "alice"
        raise failure()

    async def stream(request, context):
        await behavior(request, context)
        yield b"unreachable"

    async def run():
        original = (grpc.unary_stream_rpc_method_handler(stream) if streaming
                    else grpc.unary_unary_rpc_method_handler(behavior))

        async def continuation(details):
            return original

        details = SimpleNamespace(method="/probe/call", invocation_metadata=())
        context = SimpleNamespace(
            auth_context=lambda: {"transport_security_type": [b"ssl"]},
            peer_identity_key=lambda: "x509_common_name",
            peer_identities=lambda: [b"alice"],
        )
        handler = await interceptor.intercept_service(continuation, details)
        with pytest.raises(failure):
            if streaming:
                [value async for value in handler.unary_stream(b"ok", context)]
            else:
                await handler.unary_unary(b"ok", context)
        assert module.get_auth_context() is None

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["unary_unary", "unary_stream", "stream_unary", "stream_stream"])
def test_synchronous_handlers_keep_executor_and_request_iterator_semantics(modules, kind):
    module = modules("marty_common.auth_interceptor")
    authorization = modules("marty_common.authorization")
    interceptor = module.AuthServerInterceptor()
    server_credentials, clients = transport_credentials()
    main_thread = threading.get_ident()
    request_streaming, response_streaming = kind.startswith("stream_"), kind.endswith("_stream")

    @authorization.require("document:read", policy_engine=SimpleNamespace(evaluate=lambda context: context.identity in clients and context.roles == []))
    def behavior(request, context):
        assert threading.get_ident() != main_thread
        identity = module.get_auth_context().identity
        time.sleep(0.01)
        values = list(request) if request_streaming else [request]
        result = identity.encode() + b":" + b"".join(values)
        return iter([result, result]) if response_streaming else result

    async def run(pool):
        server = grpc.aio.server(migration_thread_pool=pool, interceptors=[interceptor])
        handler = getattr(grpc, kind + "_rpc_method_handler")(behavior)
        server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("probe", {"call": handler}),))
        port = server.add_secure_port("127.0.0.1:0", server_credentials)
        await server.start()
        try:
            async def invoke(identity):
                async with grpc.aio.secure_channel(f"localhost:{port}", clients[identity]) as channel:
                    response = getattr(channel, kind)("/probe/call")(
                        iter([b"ok"]) if request_streaming else b"ok", timeout=5)
                    return [value async for value in response] if response_streaming else await response

            result = await asyncio.gather(invoke("alice"), invoke("bob"))
            expected = [b"alice:ok", b"bob:ok"]
            assert result == ([[value, value] for value in expected] if response_streaming else expected)
        finally:
            await server.stop(0)
        assert module.get_auth_context() is None

    with ThreadPoolExecutor(max_workers=2) as pool:
        asyncio.run(run(pool))
