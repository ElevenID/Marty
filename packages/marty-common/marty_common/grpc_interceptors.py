"""Common gRPC server interceptors."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable

import grpc
from grpc import aio as grpc_aio

from marty_common.exceptions import MartyServiceException

LOGGER = logging.getLogger(__name__)


class ExceptionToStatusInterceptor(grpc.ServerInterceptor):
    """Translate application exceptions into canonical gRPC status codes."""

    def intercept_service(self, continuation, handler_call_details):  # type: ignore[override]
        handler = continuation(handler_call_details)
        if handler is None:
            return None

        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(
                self._wrap_unary_stream(handler.unary_stream),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(
                self._wrap_stream_unary(handler.stream_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_stream:
            return grpc.stream_stream_rpc_method_handler(
                self._wrap_stream_stream(handler.stream_stream),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler

    def _wrap_unary_unary(self, func: Callable):
        def _wrapper(request, context):
            try:
                return func(request, context)
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper

    def _wrap_unary_stream(self, func: Callable):
        def _wrapper(request, context):
            try:
                yield from func(request, context)
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper

    def _wrap_stream_unary(self, func: Callable):
        def _wrapper(request_iterator, context):
            try:
                return func(request_iterator, context)
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper

    def _wrap_stream_stream(self, func: Callable):
        def _wrapper(request_iterator, context):
            try:
                yield from func(request_iterator, context)
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper


class AsyncExceptionToStatusInterceptor(grpc_aio.ServerInterceptor):
    """Async variant translating application exceptions into gRPC status codes."""

    async def intercept_service(self, continuation, handler_call_details):  # type: ignore[override]
        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        if handler.unary_unary:
            return grpc_aio.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:
            return grpc_aio.unary_stream_rpc_method_handler(
                self._wrap_unary_stream(handler.unary_stream),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_unary:
            return grpc_aio.stream_unary_rpc_method_handler(
                self._wrap_stream_unary(handler.stream_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_stream:
            return grpc_aio.stream_stream_rpc_method_handler(
                self._wrap_stream_stream(handler.stream_stream),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler

    def _wrap_unary_unary(self, func: Callable):
        async def _wrapper(request, context):
            try:
                result = func(request, context)
                return await _maybe_await(result)
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                await context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper

    def _wrap_unary_stream(self, func: Callable):
        async def _wrapper(request, context):
            try:
                async for item in _async_iter(func(request, context)):
                    yield item
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                await context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper

    def _wrap_stream_unary(self, func: Callable):
        async def _wrapper(request_iterator, context):
            try:
                result = func(request_iterator, context)
                return await _maybe_await(result)
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                await context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper

    def _wrap_stream_stream(self, func: Callable):
        async def _wrapper(request_iterator, context):
            try:
                async for item in _async_iter(func(request_iterator, context)):
                    yield item
            except MartyServiceException as exc:  # pylint: disable=except-general
                LOGGER.warning("Application error: %s", exc)
                await context.abort(exc.status_code or grpc.StatusCode.INTERNAL, exc.message)
            except grpc.RpcError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Unhandled server exception")
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _wrapper


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def _async_iter(result):
    if hasattr(result, "__aiter__"):
        async for item in result:
            yield item
    else:
        for item in result:
            yield item


__all__ = ["AsyncExceptionToStatusInterceptor", "ExceptionToStatusInterceptor"]
