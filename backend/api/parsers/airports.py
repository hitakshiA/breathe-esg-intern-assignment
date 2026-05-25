"""IATA airport coordinates for Haversine distance calculation."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

# Subset chosen to cover the demo sample data + most-used corporate routes.
# Production would load a full OurAirports/OpenFlights dataset.
COORDS: dict[str, tuple[float, float]] = {
    # UK / Europe
    "LHR": (51.4775, -0.4614),    "LGW": (51.1481, -0.1903),
    "MAN": (53.3537, -2.2750),    "EDI": (55.9500, -3.3725),
    "CDG": (49.0097,  2.5479),    "ORY": (48.7253,  2.3594),
    "AMS": (52.3086,  4.7639),    "FRA": (50.0379,  8.5622),
    "MUC": (48.3538, 11.7861),    "ZRH": (47.4582,  8.5555),
    "MAD": (40.4983, -3.5676),    "BCN": (41.2974,  2.0833),
    "DUB": (53.4264, -6.2499),    "FCO": (41.8003, 12.2389),
    # Americas
    "JFK": (40.6413, -73.7781),   "EWR": (40.6895, -74.1745),
    "LGA": (40.7769, -73.8740),   "ORD": (41.9742, -87.9073),
    "LAX": (33.9425, -118.4081),  "SFO": (37.6213, -122.3790),
    "SEA": (47.4502, -122.3088),  "ATL": (33.6407, -84.4277),
    "DFW": (32.8998, -97.0403),   "MIA": (25.7959, -80.2870),
    "BOS": (42.3656, -71.0096),   "IAD": (38.9531, -77.4565),
    "YYZ": (43.6777, -79.6248),   "MEX": (19.4360, -99.0719),
    # Middle East / India
    "DXB": (25.2532, 55.3657),    "AUH": (24.4330, 54.6511),
    "DOH": (25.2606, 51.6138),    "DEL": (28.5562, 77.1000),
    "BOM": (19.0896, 72.8656),    "BLR": (13.1986, 77.7066),
    "MAA": (12.9941, 80.1709),    "HYD": (17.2403, 78.4294),
    # Asia / APAC
    "SIN": (1.3644, 103.9915),    "HKG": (22.3080, 113.9185),
    "NRT": (35.7720, 140.3929),   "HND": (35.5494, 139.7798),
    "ICN": (37.4602, 126.4407),   "PVG": (31.1443, 121.8083),
    "BKK": (13.6900, 100.7501),   "KUL": (2.7456, 101.7099),
    "SYD": (-33.9399, 151.1753),  "MEL": (-37.6690, 144.8410),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points in kilometres."""
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


def flight_distance_km(origin: str, destination: str) -> Optional[float]:
    """Returns great-circle distance + DEFRA 8% detour uplift, or None."""
    a = COORDS.get(origin.upper())
    b = COORDS.get(destination.upper())
    if not a or not b:
        return None
    gc = haversine_km(a, b)
    return round(gc * 1.08, 2)  # DEFRA recommends 8% uplift for non-direct routing.
