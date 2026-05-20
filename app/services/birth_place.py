"""Привязка места рождения к координатам для расчётов."""

from __future__ import annotations

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from app.services.city_catalog import resolve_city_catalog

_NOMINATIM_USER_AGENT = "TaroApp/1.0 (tarot)"


def resolve_city_coordinates(city: str) -> tuple[float, float] | None:
    """Возвращает (lat, lon) по названию города или None."""
    if not city or not city.strip():
        return None
    coords = resolve_city_catalog(city.strip())
    if coords:
        return coords
    try:
        geolocator = Nominatim(user_agent=_NOMINATIM_USER_AGENT)
        loc = geolocator.geocode(city.strip(), timeout=8)
        if loc:
            return (loc.latitude, loc.longitude)
    except (GeocoderTimedOut, GeocoderServiceError, Exception):
        pass
    return None


def coerce_birth_place_coords(
    city: str,
    lat: float | None,
    lon: float | None,
) -> tuple[float | None, float | None]:
    """
    Возвращает (lat, lon) или (None, None), если место нельзя однозначно привязать.
    Пустой город: (None, None).
    Если переданы валидные lat/lon, они имеют приоритет над геокодингом по строке.
    """
    c = (city or "").strip()
    if not c:
        return (None, None)
    if lat is not None and lon is not None:
        try:
            la = float(lat)
            lo = float(lon)
        except (TypeError, ValueError):
            la, lo = None, None
        else:
            if -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0:
                return (la, lo)
    coords = resolve_city_coordinates(c)
    if coords:
        return (float(coords[0]), float(coords[1]))
    return (None, None)


def normalize_stored_birth_place(
    city_raw: str,
    birth_lat: float | None,
    birth_lon: float | None,
) -> tuple[str | None, float | None, float | None]:
    """
    Город в БД храним только вместе с координатами.
    Возвращает (строка города, lat, lon) или (None, None, None), если привязать нельзя.
    """
    c = (city_raw or "").strip()
    if not c:
        return (None, None, None)
    la, lo = coerce_birth_place_coords(c, birth_lat, birth_lon)
    if la is not None and lo is not None:
        return (c, la, lo)
    return (None, None, None)
