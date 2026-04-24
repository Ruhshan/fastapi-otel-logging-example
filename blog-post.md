# Adding trace_id and span_id to FastAPI Logs with OpenTelemetry

When you're running multiple services, a single user request can generate logs across several of them. Without a shared identifier tying those logs together, debugging becomes a guessing game. That's what distributed tracing solves — every log line gets a `trace_id` that follows the request across service boundaries.

In this guide, we'll add OpenTelemetry tracing to a FastAPI app so that every log line includes `trace_id` and `span_id`. We'll build it step by step, starting from scratch.

---

## Step 1: A Bare FastAPI Project

Start with a minimal app and one endpoint:

```python
# app/main.py
from fastapi import FastAPI

app = FastAPI(title="FastAPI OTel Logging Example")

@app.get("/weather")
async def get_weather():
    return {"temperature": 12.3, "windspeed": 7.5}
```

Run it:

```bash
pip install fastapi uvicorn
uvicorn app.main:app --reload
```

Curl it:

```bash
curl http://localhost:8000/weather
```

Uvicorn prints its default access log. No trace IDs, no structured format. Let's fix that.

---

## Step 2: Add Structured Logging

Create a logging configuration that gives us control over the log format:

```python
# app/logging_config.py
import logging
import sys

LOG_FORMAT = (
    "%(asctime)s "
    "[%(levelname)s] "
    "%(name)s: %(message)s"
)

def configure_logging(log_level: int = logging.DEBUG) -> None:
    formatter = logging.Formatter(LOG_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(stream_handler)

    # Override uvicorn's own loggers to use our formatter
    for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uvicorn_logger)
        uv_logger.handlers = [stream_handler]
        uv_logger.propagate = False
```

The uvicorn override is important. Uvicorn creates its own loggers with their own handlers. If you don't replace them, your formatter won't apply to request logs.

Call it at startup in `main.py`:

```python
# app/main.py
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(title="FastAPI OTel Logging Example")
```

Now add a logger in the route:

```python
# app/routers/weather.py
import logging
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/weather")
async def get_weather(
    lat: float = Query(default=51.5),
    lon: float = Query(default=-0.1),
):
    logger.info("Received weather request for lat=%s, lon=%s", lat, lon)
    return {"temperature": 12.3, "windspeed": 7.5}
```

Output:

```
2026-03-27 12:00:00,123 [INFO] app.routers.weather: Received weather request for lat=51.5, lon=-0.1
```

Clean, structured — but no trace context yet.

---

## Step 3: Install OpenTelemetry

We need three packages:

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-httpx
```

Note: we are **not** installing `opentelemetry-instrumentation-logging`. You'll see why in the gotchas section.

---

## Step 4: Set Up TracerProvider and Propagation

Add the OTel setup to `main.py`:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.logging_config import configure_logging

# 1. Configure logging first
configure_logging()

# 2. Set up tracer provider and propagation
provider = TracerProvider()
trace.set_tracer_provider(provider)
set_global_textmap(TraceContextTextMapPropagator())
```

Three things happen here:

- `TracerProvider` manages the lifecycle of spans (start, end, export).
- `trace.set_tracer_provider(provider)` makes it the global tracer.
- `TraceContextTextMapPropagator` reads the W3C `traceparent` header from incoming HTTP requests. This is how trace context propagates across services.

The order matters. The `TracerProvider` must be set **before** we instrument FastAPI.

---

## Step 5: Instrument FastAPI

One line, added **after** the tracer provider is set:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI(title="FastAPI OTel Logging Example")
# ... include routers ...

FastAPIInstrumentor.instrument_app(app)
```

This wraps every incoming request in an OTel span automatically. The span captures the HTTP method, route, status code, and timing.

Restart and curl:

```bash
curl http://localhost:8000/weather
```

```
2026-03-27 12:00:00,123 [INFO] app.routers.weather: Received weather request for lat=51.5, lon=-0.1
```

Still no `trace_id` in the log. The span exists (OTel is creating it), but the logging system doesn't know about it. That's the next step.

---

## Step 6: Inject Trace Context into Logs

This is the key part of the entire setup.

We need a bridge between OTel (which manages spans) and Python's `logging` (which formats log lines). The bridge is a custom `logging.Filter`:

```python
# app/logging_config.py
from opentelemetry import trace

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
```

How it works:

1. `trace.get_current_span()` reads from Python's `contextvars` — the same mechanism that makes `async/await` context-safe.
2. `get_span_context()` returns the trace ID and span ID from the active span.
3. `format(ctx.trace_id, "032x")` converts the 128-bit integer to the standard 32-character hex string.
4. We attach these as attributes on the log record, so the formatter can use them.

Now update `configure_logging` to use the filter and include trace fields in the format:

```python
LOG_FORMAT = (
    "%(asctime)s "
    "[%(levelname)s] "
    "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] "
    "%(name)s: %(message)s"
)

def configure_logging(log_level: int = logging.DEBUG) -> None:
    formatter = logging.Formatter(LOG_FORMAT)
    otel_filter = OTelContextFilter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(otel_filter)
    # ... rest stays the same
```

Restart and curl:

```bash
curl http://localhost:8000/weather
```

```
2026-03-27 12:00:00,123 [INFO] [trace_id=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6 span_id=1a2b3c4d5e6f7a8b] app.routers.weather: Received weather request for lat=51.5, lon=-0.1
```

There it is. The `trace_id` is auto-generated by OTel since we didn't provide one. Startup logs will show `trace_id=N/A` — that's expected, there's no request context during boot.

---

## Step 7: Add Spans to Service Methods

The route handler runs inside the auto-created FastAPI span. For deeper tracing, create child spans on service methods using the `@tracer.start_as_current_span` decorator:

```python
# app/services/weather_service.py
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class WeatherService:
    @tracer.start_as_current_span("get_forecast")
    async def get_forecast(self, lat: float, lon: float) -> dict:
        logger.info("Fetching forecast for lat=%s, lon=%s", lat, lon)
        # ... implementation
```

The `trace_id` stays the same across the router and service logs, but the `span_id` changes — each span gets its own ID within the trace.

```
[trace_id=aaa...aaa span_id=1111111111111111] app.routers.weather: Received weather request
[trace_id=aaa...aaa span_id=2222222222222222] app.services.weather_service: Fetching forecast
```

---

## Step 8: Async HTTP Call (Weather API)

Replace the hardcoded response with a real async HTTP call to the [Open-Meteo API](https://open-meteo.com/) (free, no key required):

```python
# app/services/weather_service.py
import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

class WeatherService:
    @tracer.start_as_current_span("get_forecast")
    async def get_forecast(self, lat: float, lon: float) -> dict:
        logger.info("Fetching forecast for lat=%s, lon=%s", lat, lon)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                OPEN_METEO_URL,
                params={"latitude": lat, "longitude": lon, "current_weather": True},
            )
            response.raise_for_status()

        data = response.json()
        logger.info("Forecast received: %s", data.get("current_weather", {}).get("temperature"))
        return data
```

Using `httpx.AsyncClient` (not `requests`) is critical. Since the call is `async`, it runs in the same event loop and context as the request handler — OTel's `contextvars`-based context is preserved. A synchronous `requests.get()` would run in a thread pool and lose the trace context.

---

## Step 9: Propagate Trace Context to Outbound Requests

At this point, our service receives `traceparent` from upstream and attaches it to logs — but it doesn't forward it to the Open-Meteo call. The downstream service has no way to join the same trace.

Fix this with `HTTPXClientInstrumentor`, which patches all `httpx` clients globally to inject the active span's `traceparent` header on every outgoing request:

```python
# app/main.py
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# 4. Instrument FastAPI and httpx (must be after TracerProvider is set)
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
```

No changes are needed in `weather_service.py`. The instrumentor hooks into httpx's transport layer and reads the active span from `contextvars` at request time — the same context that was propagated from the inbound `traceparent`.

To verify, check the downstream server's logs. They'll show the same `trace_id` that your service received from its caller, forming an unbroken chain across all three hops.

---

## Step 10: Test with the `traceparent` Header

In a real system, an upstream service sends the `traceparent` header so all downstream logs share the same `trace_id`. Let's simulate that:

```bash
curl -H "traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01" \
  "http://localhost:8000/weather?lat=51.5&lon=-0.1"
```

The `traceparent` format is `version-traceId-parentSpanId-flags`:

| Field | Value | Meaning |
|---|---|---|
| `00` | version | Always `00` |
| `aaaa...` | trace_id | 32-hex-char trace identifier |
| `bbbb...` | parent_span_id | 16-hex-char parent span ID |
| `01` | flags | `01` = sampled |

Expected logs:

```
[trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa span_id=c1d2e3f4a5b6c7d8] app.routers.weather: Received weather request for lat=51.5, lon=-0.1
[trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa span_id=1a2b3c4d5e6f7a8b] app.services.weather_service: Fetching forecast for lat=51.5, lon=-0.1
[trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa span_id=1a2b3c4d5e6f7a8b] app.services.weather_service: Forecast received: 12.3
```

The `trace_id` matches what we sent. Propagation works.

---

## Gotchas and Lessons Learned

### 1. `LoggingInstrumentor` is unreliable

OpenTelemetry provides `opentelemetry-instrumentation-logging` with a `LoggingInstrumentor` that claims to auto-inject `otelTraceID` into log records. In practice, the fields were empty or missing even with active spans. The custom `OTelContextFilter` approach shown above is more reliable and more transparent — you can see exactly what it does.

### 2. Sync calls in async handlers lose OTel context

If you call a synchronous function (e.g., `requests.get()`, or a LangChain `agent.invoke()`) from an async FastAPI handler, it may run in a thread pool. The OTel context stored in `contextvars` does not always propagate to that thread, so logs inside the sync call show `trace_id=N/A`. Fix: use async variants (`httpx`, `agent.ainvoke()`).

### 3. TracerProvider must be set before FastAPIInstrumentor

If you call `FastAPIInstrumentor.instrument_app(app)` before setting the `TracerProvider`, the auto-created spans use a no-op tracer and produce invalid span contexts. Always set the provider first.

### 4. Uvicorn loggers need explicit handler override

Uvicorn creates its own loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) with their own handlers. Configuring the root logger does not affect them. You must replace their handlers:

```python
for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    uv_logger = logging.getLogger(uvicorn_logger)
    uv_logger.handlers = [stream_handler]
    uv_logger.propagate = False
```

### 5. Startup logs will show `trace_id=N/A`

This is expected. During application startup, there's no incoming request and no active span. The `OTelContextFilter` defaults to `N/A`. Trace IDs only appear for logs emitted during request handling.

---

## Summary

The complete setup is:

1. **`logging.Formatter`** with `%(otelTraceID)s` and `%(otelSpanID)s` in the format string
2. **`OTelContextFilter`** that reads the active span via `trace.get_current_span()` and injects IDs into the log record
3. **`TracerProvider`** + **`TraceContextTextMapPropagator`** for W3C `traceparent` header propagation
4. **`FastAPIInstrumentor`** to auto-create spans per request
5. **`@tracer.start_as_current_span`** on service methods for finer-grained tracing
6. **`HTTPXClientInstrumentor`** to forward the active trace context to all outbound httpx requests

The full working example is available in the [sample project](https://github.com/your-repo/fastapi-otel-logging-example).