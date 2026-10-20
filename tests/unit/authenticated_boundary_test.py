"""Exercise actual gRPC dispatch, trusted transport identity and native verifiers."""

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


def jwt_interceptor(module, monkeypatch):
    requests = []

    def validate(value):
        request = json.loads(value)
        requests.append(request)
        if request["compact_jwt"] not in {"alice", "bob"}:
            raise ValueError("bad signature")
        return json.dumps({"sub": request["compact_jwt"], "roles": ["reader"]})

    monkeypatch.setattr(module, "load_native_backend", lambda *args: SimpleNamespace(oidc_validate_id_token=validate))
    interceptor = module.AuthServerInterceptor(jwt_jwks={"keys": [{"kty": "RSA", "kid": "test"}]},
                                               jwt_issuer="https://issuer.test", jwt_audience="grpc")
    return interceptor, requests


@pytest.mark.parametrize("kind", ["unary_unary", "unary_stream", "stream_unary", "stream_stream"])
def test_real_rpc_shapes_scope_authorization_and_reject_forged_credentials(modules, monkeypatch, kind):
    module = modules("marty_common.auth_interceptor")
    authorization = modules("marty_common.authorization")
    interceptor, validations = jwt_interceptor(module, monkeypatch)
    observed = []

    def evaluate(context):
        observed.append((context.identity, context.roles))
        return context.roles == ["reader"]

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
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        try:
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                async def invoke(identity):
                    call = getattr(channel, kind)("/probe/call")
                    response = call(iter([b"ok"]) if request_streaming else b"ok",
                                    metadata=(("authorization", "Bearer " + identity),), timeout=5)
                    return [value async for value in response] if response_streaming else await response

                results = await asyncio.gather(invoke("alice"), invoke("bob"))
                expected = [b"alice:ok", b"bob:ok"]
                assert results == ([[value, value] for value in expected] if response_streaming else expected)
                for metadata in ((), (("x-client-cert-subject", "admin"),),
                                 (("authorization", "Bearer forged"),),
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
    assert sorted(observed) == [("alice", ["reader"]), ("bob", ["reader"])]
    assert all(request["expected_issuer"] == "https://issuer.test" and request["expected_audience"] == "grpc"
               and request["leeway_seconds"] == 0 for request in validations)
    # Merely constructing an interceptor does not make raw metadata trusted.
    with pytest.raises(authorization.AuthorizationError):
        asyncio.run(authorized(b"ok", SimpleNamespace(invocation_metadata=lambda: (("authorization", "Bearer alice"),))))


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


def test_native_jwt_enforces_signature_issuer_audience_and_expiry(modules):
    if os.environ.get("CI") == "true":
        importlib.import_module("_marty_rs")
    else:
        pytest.importorskip("_marty_rs", reason="Pinned native wheel required; installed in mandatory CI test lane")
    import jwt

    module = modules("marty_common.auth_interceptor")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": "test"}
    interceptor = module.AuthServerInterceptor(jwt_jwks={"keys": [public]}, jwt_issuer="https://issuer.test", jwt_audience="grpc")
    claims = {"sub": "alice", "roles": ["reader"], "iss": "https://issuer.test", "aud": "grpc",
              "iat": int(time.time()), "exp": int(time.time()) + 300}

    async def validate(payload, signing_key=key):
        token = jwt.encode(payload, signing_key, algorithm="RS256", headers={"kid": "test"})
        return await interceptor._authenticate_jwt({"authorization": "Bearer " + token})

    assert asyncio.run(validate(claims)).identity == "alice"
    for change in ({"iss": "https://evil.test"}, {"aud": "other"}, {"exp": 1}, {"iat": int(time.time()) + 600}):
        assert not asyncio.run(validate(claims | change)).authenticated
    assert not asyncio.run(validate({k: v for k, v in claims.items() if k != "exp"})).authenticated
    assert not asyncio.run(validate(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048))).authenticated


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
    interceptor, _ = jwt_interceptor(module, monkeypatch)

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

        details = SimpleNamespace(method="/probe/call", invocation_metadata=(("authorization", "Bearer alice"),))
        handler = await interceptor.intercept_service(continuation, details)
        with pytest.raises(failure):
            if streaming:
                [value async for value in handler.unary_stream(b"ok", SimpleNamespace())]
            else:
                await handler.unary_unary(b"ok", SimpleNamespace())
        assert module.get_auth_context() is None

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["unary_unary", "unary_stream", "stream_unary", "stream_stream"])
def test_synchronous_handlers_keep_executor_and_request_iterator_semantics(modules, monkeypatch, kind):
    module = modules("marty_common.auth_interceptor")
    authorization = modules("marty_common.authorization")
    interceptor, _ = jwt_interceptor(module, monkeypatch)
    main_thread = threading.get_ident()
    request_streaming, response_streaming = kind.startswith("stream_"), kind.endswith("_stream")

    @authorization.require("document:read", policy_engine=SimpleNamespace(evaluate=lambda context: context.roles == ["reader"]))
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
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        try:
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                async def invoke(identity):
                    response = getattr(channel, kind)("/probe/call")(
                        iter([b"ok"]) if request_streaming else b"ok",
                        metadata=(("authorization", "Bearer " + identity),), timeout=5)
                    return [value async for value in response] if response_streaming else await response

                result = await asyncio.gather(invoke("alice"), invoke("bob"))
                expected = [b"alice:ok", b"bob:ok"]
                assert result == ([[value, value] for value in expected] if response_streaming else expected)
        finally:
            await server.stop(0)
        assert module.get_auth_context() is None

    with ThreadPoolExecutor(max_workers=2) as pool:
        asyncio.run(run(pool))
