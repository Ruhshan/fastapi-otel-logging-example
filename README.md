# FastAPI + OpenTelemetry Logging Example

A minimal FastAPI app demonstrating how to inject `trace_id` and `span_id` into every log line using OpenTelemetry.

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

Plain request (OTel generates a trace_id automatically):

```bash
curl "http://localhost:8000/weather?lat=51.5&lon=-0.1"
```

With a `traceparent` header (your trace_id propagates into logs):

```bash
curl -H "traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01" \
  "http://localhost:8000/weather?lat=51.5&lon=-0.1"
```

## Expected Log Output

```
2026-03-27 12:00:00,123 [INFO] [trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa span_id=c1d2e3f4a5b6c7d8] app.routers.weather: Received weather request for lat=51.5, lon=-0.1
2026-03-27 12:00:00,124 [INFO] [trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa span_id=1a2b3c4d5e6f7a8b] app.services.weather_service: Fetching forecast for lat=51.5, lon=-0.1
2026-03-27 12:00:00,456 [INFO] [trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa span_id=1a2b3c4d5e6f7a8b] app.services.weather_service: Forecast received: 12.3
```

Notice: same `trace_id` across router and service, different `span_id` per span.

## How It Works

See the accompanying [blog post](blog-post.md) for a step-by-step guide.