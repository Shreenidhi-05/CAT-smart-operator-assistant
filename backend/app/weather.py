import httpx

from .config import DEFAULT_LAT, DEFAULT_LON, OPENWEATHER_API_KEY

# Per-zone fallback conditions used when no API key is configured (or the API fails).
# "Zone C - Ridge" is intentionally hazardous so the risk-check demo is reproducible.
ZONE_FALLBACK = {
    "Zone A - Pit": dict(temp_c=24.0, wind_kmh=12.0, visibility_m=8000, condition="Clear", humidity=45),
    "Zone B - Haul Road": dict(temp_c=23.0, wind_kmh=18.0, visibility_m=6000, condition="Clouds", humidity=55),
    "Zone C - Ridge": dict(temp_c=14.0, wind_kmh=58.0, visibility_m=40, condition="Fog", humidity=95),
    "Zone D - Stockpile": dict(temp_c=25.0, wind_kmh=9.0, visibility_m=9000, condition="Clear", humidity=40),
}
DEFAULT_WEATHER = dict(temp_c=22.0, wind_kmh=10.0, visibility_m=10000, condition="Clear", humidity=50)


async def get_weather(zone: str | None = None) -> dict:
    if OPENWEATHER_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"lat": DEFAULT_LAT, "lon": DEFAULT_LON, "appid": OPENWEATHER_API_KEY, "units": "metric"},
                )
                r.raise_for_status()
                j = r.json()
                return dict(
                    temp_c=j["main"]["temp"], wind_kmh=round(j["wind"]["speed"] * 3.6, 1),
                    visibility_m=j.get("visibility", 10000), condition=j["weather"][0]["main"],
                    humidity=j["main"]["humidity"], source="openweathermap",
                )
        except Exception:
            pass
    w = dict(ZONE_FALLBACK.get(zone or "", DEFAULT_WEATHER))
    w["source"] = "fallback"
    return w
