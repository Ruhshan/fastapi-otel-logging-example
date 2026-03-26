import logging

from fastapi import APIRouter, Query

from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)
router = APIRouter()
service = WeatherService()


@router.get("/weather")
async def get_weather(
    lat: float = Query(default=51.5, description="Latitude"),
    lon: float = Query(default=-0.1, description="Longitude"),
):
    logger.info("Received weather request for lat=%s, lon=%s", lat, lon)
    data = await service.get_forecast(lat, lon)
    return data.get("current_weather", {})