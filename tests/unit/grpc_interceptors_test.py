"""Exercise the public async interceptor through real gRPC handlers and RPCs."""

from types import SimpleNamespace

import grpc
import pytest

from marty_common.exceptions import InvalidInputError
from marty_common.grpc_interceptors import AsyncExceptionToStatusInterceptor


CARDINALITIES = ("unary_unary", "unary_stream", "stream_unary", "stream_stream")


@pytest.mark.asyncio
@pytest.mark.parametrize("cardinality", CARDINALITIES)
async def test_async_handler_keeps_cardinality_and_codecs(cardinality):
    async def implementation(request, context):
        return request

    def deserialize(value):
        return value.decode()

    def serialize(value):
        return value.encode()

    original = getattr(grpc, f"{cardinality}_rpc_method_handler")(
        implementation,
        request_deserializer=deserialize,
        response_serializer=serialize,
    )
    details = SimpleNamespace(method="/test.Runtime/echo", invocation_metadata=())
    continued = []

    async def continuation(received):
        continued.append(received)
        return original

    wrapped = await AsyncExceptionToStatusInterceptor().intercept_service(continuation, details)
    assert continued == [details]
    assert wrapped.request_streaming == original.request_streaming
    assert wrapped.response_streaming == original.response_streaming
    assert wrapped.request_deserializer is deserialize
    assert wrapped.response_serializer is serialize
    assert getattr(wrapped, cardinality) is not implementation


@pytest.mark.asyncio
async def test_unknown_async_method_remains_unhandled():
    async def continuation(details):
        return None

    assert await AsyncExceptionToStatusInterceptor().intercept_service(continuation, None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cardinality", CARDINALITIES)
@pytest.mark.parametrize("failure", [None, "application", "unexpected"])
async def test_async_rpc_success_and_exception_status(cardinality, failure):
    def respond(request):
        if failure == "application":
            raise InvalidInputError("invalid request")
        if failure == "unexpected":
            raise RuntimeError("dependency failed")
        return request + 1

    async def unary_unary(request, context):
        return respond(request)

    async def unary_stream(request, context):
        yield respond(request)

    async def stream_unary(requests, context):
        values = [request async for request in requests]
        return respond(sum(values))

    async def stream_stream(requests, context):
        async for request in requests:
            yield respond(request)

    implementations = {
        "unary_unary": unary_unary,
        "unary_stream": unary_stream,
        "stream_unary": stream_unary,
        "stream_stream": stream_stream,
    }
    handler = getattr(grpc, f"{cardinality}_rpc_method_handler")(
        implementations[cardinality],
        request_deserializer=lambda value: int(value.decode()),
        response_serializer=lambda value: str(value).encode(),
    )
    server = grpc.aio.server(interceptors=[AsyncExceptionToStatusInterceptor()])
    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("test.Runtime", {"echo": handler}),)
    )
    port = server.add_insecure_port("127.0.0.1:0")
    assert port > 0
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            rpc = getattr(channel, cardinality)(
                "/test.Runtime/echo",
                request_serializer=lambda value: str(value).encode(),
                response_deserializer=lambda value: int(value.decode()),
            )
            request = iter([7]) if cardinality.startswith("stream_") else 7

            async def invoke():
                call = rpc(request, timeout=5)
                if cardinality.endswith("_stream"):
                    return [item async for item in call]
                return [await call]

            if failure is None:
                assert await invoke() == [8]
            else:
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await invoke()
                expected = (
                    grpc.StatusCode.INVALID_ARGUMENT
                    if failure == "application"
                    else grpc.StatusCode.INTERNAL
                )
                assert caught.value.code() == expected
                assert caught.value.details() == (
                    "invalid request" if failure == "application" else "dependency failed"
                )
    finally:
        await server.stop(0)
