import asyncio
import logging
import queue
import sys
import threading
from datetime import datetime, timezone

import grpc

# Try different import paths for proto files depending on the environment
try:
    # First try the standard src.proto path (development)
    from marty_plugin.proto import (
        common_services_pb2,  # type: ignore
        common_services_pb2_grpc,  # type: ignore
    )
except ImportError:
    try:
        # Try the proto path for Docker environment
        from marty_plugin.proto import (
            common_services_pb2,  # type: ignore
            common_services_pb2_grpc,  # type: ignore
        )
    except ImportError:
        # Try relative import
        from marty_plugin.proto.v1 import common_services_pb2, common_services_pb2_grpc

# Maximum number of log entries to queue per client.
# If a client falls behind, older messages might be dropped or it might block.
# For simplicity, we'll use a large enough queue for now.
MAX_CLIENT_QUEUE_SIZE = 1000


class GrpcLogHandler(logging.Handler):
    """
    A logging handler that forwards log records to gRPC clients
    subscribed to the log stream.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name
        self._client_queues = []
        self._lock = threading.Lock()

    def add_client_queue(self, client_queue: queue.Queue) -> None:
        """Adds a queue for a new gRPC client subscriber."""
        with self._lock:
            self._client_queues.append(client_queue)
        # Log locally that a client has subscribed
        logging.getLogger(__name__).info(
            f"gRPC log stream client subscribed. Total subscribers: {len(self._client_queues)}"
        )

    def remove_client_queue(self, client_queue: queue.Queue) -> None:
        """Removes a queue for a gRPC client that has disconnected."""
        with self._lock:
            try:
                self._client_queues.remove(client_queue)
            except ValueError:
                # Queue already removed or was never there, ignore.
                pass
        logging.getLogger(__name__).info(
            f"gRPC log stream client unsubscribed. Total subscribers: {len(self._client_queues)}"
        )

    def emit(self, record: logging.LogRecord) -> None:
        """
        Formats the log record as a LogEntry protobuf message and
        puts it into each subscribed client's queue.
        """
        try:
            log_entry = common_services_pb2.LogEntry(  # type: ignore
                level=record.levelname,
                service_name=getattr(
                    record, "service_name", self.service_name
                ),  # Get service_name from record if available
                logger_name=record.name,
                message=self.format(record),  # Use handler's formatter or default
            )
            # Set timestamp
            log_entry.timestamp.FromDatetime(
                datetime.fromtimestamp(record.created, tz=timezone.utc)
            )

            # Add other structured information if available in the record
            if hasattr(record, 'request_id'):
                log_entry.metadata['request_id'] = record.request_id

            with self._lock:
                # Iterate over a copy of the list in case it's modified during iteration (though lock should prevent)
                for client_q in list(self._client_queues):
                    try:
                        client_q.put_nowait(log_entry)
                    except queue.Full:
                        # Log locally that a client's queue is full and a message was dropped.
                        # Avoid logging through the same handler to prevent recursion if this logger also uses it.
                        print(
                            f"WARNING: Client log queue full for {self.service_name}. Log message dropped for a subscriber.",
                            file=sys.stderr,
                        )
                    except Exception as e:
                        # Handle other potential errors, e.g., if the queue is somehow closed.
                        print(
                            f"ERROR: Could not put log into client queue for {self.service_name}: {e}",
                            file=sys.stderr,
                        )
        except Exception as e:
            # Handle errors during log record processing itself.
            # This is important to prevent the logging system from crashing the application.
            # Using print directly to avoid recursion if this handler is part of the failing log path.
            print(f"ERROR: Failed to process log record in GrpcLogHandler: {e}", file=sys.stderr)
            # Optionally, call self.handleError(record) if you have specific error handling.


# Global instance of the GrpcLogHandler.
# This will be initialized by setup_logging with the correct service name.
# We define it as None initially and let setup_logging create it.
grpc_log_handler_instance: GrpcLogHandler = None


def get_grpc_log_handler() -> GrpcLogHandler:
    """Returns the global GrpcLogHandler instance."""
    if grpc_log_handler_instance is None:
        # This is a fallback, ideally setup_logging should have initialized it.
        # This might happen if a module tries to get it before setup_logging is called,
        # or if setup_logging is not called in some execution paths (e.g. unit tests not using main).
        # Consider logging a warning here or raising an error if strict initialization is required.
        print(
            "WARNING: GrpcLogHandler accessed before proper initialization. Using default service name.",
            file=sys.stderr,
        )
        # Cannot initialize it here properly without service_name.
        # This indicates a potential issue in the application's startup sequence.
        # For now, we'll allow it but it won't have the correct service_name from env.
        # A better approach might be to have setup_logging return it or pass it explicitly.
        # For now, let's assume it will be set by setup_logging.
    return grpc_log_handler_instance


class LoggingStreamerServicer(common_services_pb2_grpc.LoggingStreamerServicer):
    """
    gRPC service that streams log entries to subscribed clients.
    """

    def __init__(self) -> None:
        # The handler instance should be set up by the main application's logging configuration.
        self.handler = get_grpc_log_handler()
        if not self.handler:
            # This is a critical issue if the handler isn't available when the servicer is instantiated.
            # It means logging to gRPC clients won't work.
            # We'll log an error to standard logging, which should go to stdout.
            logging.error("GrpcLogHandler not initialized. Log streaming will not work.")

    async def StreamLogs(self, request: common_services_pb2.StreamLogsRequest, context):  # type: ignore
        """
        Called by a gRPC client to subscribe to the log stream.
        Maintains a queue for the client and yields log entries as they arrive.
        """
        if not self.handler:
            logging.error("StreamLogs called but GrpcLogHandler is not initialized.")
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Log streaming service not available due to internal error.",
            )
            return  # pragma: no cover - abort raises

        client_log_queue = queue.Queue(maxsize=MAX_CLIENT_QUEUE_SIZE)
        self.handler.add_client_queue(client_log_queue)

        peer = context.peer()
        logging.info(f"Client {peer} subscribed to log stream.")

        try:
            while True:
                try:
                    log_entry = await asyncio.to_thread(
                        client_log_queue.get, True, 1
                    )  # Timeout to allow checking context.is_active()
                    yield log_entry
                except queue.Empty:
                    # Timeout occurred, check if client is still active
                    if not context.is_active():
                        logging.info(
                            f"Client {peer} disconnected from log stream (context inactive)."
                        )
                        break
                    continue  # Continue waiting for logs
                except Exception as e:  # Catch any other exception from queue.get or yield
                    logging.exception(f"Error during log streaming for client {peer}")
                    await context.abort(grpc.StatusCode.INTERNAL, f"Error during streaming: {e}")
                    break
        except Exception as e:
            # Catch-all for unexpected errors in the streaming loop
            logging.error(f"Unexpected error in StreamLogs for client {peer}: {e}", exc_info=True)
        finally:
            self.handler.remove_client_queue(client_log_queue)
            logging.info(f"Client {peer} unsubscribed from log stream. Queue removed.")
