from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.logging_config import configure_logging
from app.routers import weather

# 1. Configure logging first
configure_logging()

# 2. Set up OpenTelemetry tracer provider and propagation
provider = TracerProvider()
trace.set_tracer_provider(provider)
set_global_textmap(TraceContextTextMapPropagator())

# 3. Create the FastAPI app
app = FastAPI(title="FastAPI OTel Logging Example")
app.include_router(weather.router)

# 4. Instrument FastAPI and httpx (must be after TracerProvider is set)
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
