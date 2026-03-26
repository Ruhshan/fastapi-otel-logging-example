import logging
import sys

from opentelemetry import trace

LOG_FORMAT = (
    "%(asctime)s "
    "[%(levelname)s] "
    "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] "
    "%(name)s: %(message)s"
)


class OTelContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            record.otelTraceID = format(ctx.trace_id, "032x")
            record.otelSpanID = format(ctx.span_id, "016x")
        else:
            record.otelTraceID = "N/A"
            record.otelSpanID = "N/A"
        return True


def configure_logging(log_level: int = logging.DEBUG) -> None:
    formatter = logging.Formatter(LOG_FORMAT)
    otel_filter = OTelContextFilter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(otel_filter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(stream_handler)

    for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uvicorn_logger)
        uv_logger.handlers = [stream_handler]
        uv_logger.propagate = False