import logging

import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

#OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_URL = "http://localhost:8088/v1/forecast"


class WeatherService:
    @tracer.start_as_current_span("get_forecast")
    async def get_forecast(self, lat: float, lon: float) -> dict:
        logger.info("Fetching forecast for lat=%s, lon=%s", lat, lon)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                OPEN_METEO_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": True,
                },
            )
            response.raise_for_status()

        data = response.json()
        logger.info("Forecast received: %s", data.get("current_weather", {}).get("temperature"))
        return data