"""
Haversine distance and ETA for delivery tracking.
"""
import math
from decimal import Decimal
from typing import Optional, Tuple

# Average speed for ETA (km/h). Configurable via Django settings if needed.
DEFAULT_AVG_SPEED_KMH = 25


def haversine_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float
) -> float:
    """
    Return great-circle distance in km between two (lat, lon) points.
    """
    R = 6371  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def haversine_km_decimal(
    lat1: Optional[Decimal], lon1: Optional[Decimal],
    lat2: Optional[Decimal], lon2: Optional[Decimal]
) -> Optional[float]:
    """Haversine with Decimal inputs; returns None if any coord is None."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    return haversine_km(float(lat1), float(lon1), float(lat2), float(lon2))


def eta_minutes(
    distance_km: float,
    avg_speed_kmh: float = DEFAULT_AVG_SPEED_KMH
) -> int:
    """Estimated time in minutes: distance / speed * 60."""
    if distance_km <= 0 or avg_speed_kmh <= 0:
        return 0
    return max(0, int(round(distance_km / avg_speed_kmh * 60)))


def compute_distance_eta(
    from_lat: Optional[Decimal], from_lon: Optional[Decimal],
    to_lat: Optional[Decimal], to_lon: Optional[Decimal],
    avg_speed_kmh: float = DEFAULT_AVG_SPEED_KMH
) -> Tuple[Optional[float], Optional[int]]:
    """
    Return (distance_km, eta_minutes) from (from_lat, from_lon) to (to_lat, to_lon).
    Either can be None if coords missing.
    """
    dist = haversine_km_decimal(from_lat, from_lon, to_lat, to_lon)
    if dist is None:
        return None, None
    eta = eta_minutes(dist, avg_speed_kmh)
    return round(dist, 2), eta
