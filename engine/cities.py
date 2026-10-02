"""
Built-in city table.

Typing latitude and longitude is the single biggest barrier to using this.
A short lookup table removes it for the overwhelming majority of inputs
without adding a network dependency or an API key.

Coordinates are WGS84 decimal degrees. Timezone is the IANA identifier used
for the local civil clock at birth.

For births before roughly 1900 the zone name is often wrong — zone local mean
time and longitude-derived local mean time differ by minutes to tens of
minutes, and that is enough to move the ascendant by several degrees. The API
and client both surface this; see test_lmt_ambiguity_is_material.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    name: str
    country: str
    latitude: float
    longitude: float
    timezone: str


def _c(name, country, lat, lon, tz):
    return City(name, country, lat, lon, tz)


CITIES: list[City] = [
    # --- India ---
    _c("Mumbai", "India", 19.0760, 72.8777, "Asia/Kolkata"),
    _c("Delhi", "India", 28.6139, 77.2090, "Asia/Kolkata"),
    _c("Bengaluru", "India", 12.9716, 77.5946, "Asia/Kolkata"),
    _c("Hyderabad", "India", 17.3850, 78.4867, "Asia/Kolkata"),
    _c("Chennai", "India", 13.0827, 80.2707, "Asia/Kolkata"),
    _c("Kolkata", "India", 22.5726, 88.3639, "Asia/Kolkata"),
    _c("Pune", "India", 18.5204, 73.8567, "Asia/Kolkata"),
    _c("Ahmedabad", "India", 23.0225, 72.5714, "Asia/Kolkata"),
    _c("Surat", "India", 21.1702, 72.8311, "Asia/Kolkata"),
    _c("Jaipur", "India", 26.9124, 75.7873, "Asia/Kolkata"),
    _c("Lucknow", "India", 26.8467, 80.9462, "Asia/Kolkata"),
    _c("Kanpur", "India", 26.4499, 80.3319, "Asia/Kolkata"),
    _c("Nagpur", "India", 21.1458, 79.0882, "Asia/Kolkata"),
    _c("Indore", "India", 22.7196, 75.8577, "Asia/Kolkata"),
    _c("Bhopal", "India", 23.2599, 77.4126, "Asia/Kolkata"),
    _c("Patna", "India", 25.5941, 85.1376, "Asia/Kolkata"),
    _c("Varanasi", "India", 25.3176, 82.9739, "Asia/Kolkata"),
    _c("Kochi", "India", 9.9312, 76.2673, "Asia/Kolkata"),
    _c("Madurai", "India", 9.9252, 78.1198, "Asia/Kolkata"),
    _c("Chandigarh", "India", 30.7333, 76.7794, "Asia/Kolkata"),
    _c("Guwahati", "India", 26.1445, 91.7362, "Asia/Kolkata"),
    _c("Thiruvananthapuram", "India", 8.5241, 76.9366, "Asia/Kolkata"),
    _c("Coimbatore", "India", 11.0168, 76.9558, "Asia/Kolkata"),
    _c("Ludhiana", "India", 30.9010, 75.8573, "Asia/Kolkata"),
    _c("Vadodara", "India", 22.3072, 73.1812, "Asia/Kolkata"),
    _c("Agra", "India", 27.1767, 78.0081, "Asia/Kolkata"),
    _c("Nashik", "India", 19.9975, 73.7898, "Asia/Kolkata"),
    _c("Ranchi", "India", 23.3441, 85.3096, "Asia/Kolkata"),
    _c("Dehradun", "India", 30.3165, 78.0322, "Asia/Kolkata"),
    _c("Udaipur", "India", 24.5854, 73.7125, "Asia/Kolkata"),
    _c("Jodhpur", "India", 26.2389, 73.0243, "Asia/Kolkata"),
    _c("Amritsar", "India", 31.6340, 74.8723, "Asia/Kolkata"),
    _c("Allahabad", "India", 25.4358, 81.8463, "Asia/Kolkata"),
    _c("Howrah", "India", 22.5958, 88.2636, "Asia/Kolkata"),
    _c("Salem", "India", 11.6643, 78.1460, "Asia/Kolkata"),
    _c("Mysore", "India", 12.2958, 76.6394, "Asia/Kolkata"),
    _c("Raipur", "India", 21.2514, 81.6296, "Asia/Kolkata"),
    _c("Jamshedpur", "India", 22.8046, 86.2029, "Asia/Kolkata"),
    _c("Gandhinagar", "India", 23.2156, 72.6369, "Asia/Kolkata"),
    _c("Panaji", "India", 15.4909, 73.8278, "Asia/Kolkata"),
    # --- United Kingdom ---
    _c("London", "United Kingdom", 51.5074, -0.1278, "Europe/London"),
    _c("Manchester", "United Kingdom", 53.4808, -2.2426, "Europe/London"),
    _c("Birmingham", "United Kingdom", 52.4862, -1.8904, "Europe/London"),
    _c("Edinburgh", "United Kingdom", 55.9533, -3.1883, "Europe/London"),
    _c("Cardiff", "United Kingdom", 51.4816, -3.1791, "Europe/London"),
    # --- United States ---
    _c("New York", "United States", 40.7128, -74.0060, "America/New_York"),
    _c("Chicago", "United States", 41.8781, -87.6298, "America/Chicago"),
    _c("Los Angeles", "United States", 34.0522, -118.2437, "America/Los_Angeles"),
    _c("San Francisco", "United States", 37.7749, -122.4194, "America/Los_Angeles"),
    _c("Boston", "United States", 42.3601, -71.0589, "America/New_York"),
    _c("Washington", "United States", 38.9072, -77.0369, "America/New_York"),
    _c("Houston", "United States", 29.7604, -95.3698, "America/Chicago"),
    _c("Seattle", "United States", 47.6062, -122.3321, "America/Los_Angeles"),
    _c("Denver", "United States", 39.7392, -104.9903, "America/Denver"),
    _c("Atlanta", "United States", 33.7490, -84.3880, "America/New_York"),
    _c("Philadelphia", "United States", 39.9526, -75.1652, "America/New_York"),
    _c("Ulm", "Germany", 48.3988, 9.9916, "Europe/Berlin"),
    # --- Europe ---
    _c("Berlin", "Germany", 52.5200, 13.4050, "Europe/Berlin"),
    _c("Munich", "Germany", 48.1351, 11.5820, "Europe/Berlin"),
    _c("Paris", "France", 48.8566, 2.3522, "Europe/Paris"),
    _c("Rome", "Italy", 41.9028, 12.4964, "Europe/Rome"),
    _c("Madrid", "Spain", 40.4168, -3.7038, "Europe/Madrid"),
    _c("Amsterdam", "Netherlands", 52.3676, 4.9041, "Europe/Amsterdam"),
    _c("Vienna", "Austria", 48.2082, 16.3738, "Europe/Vienna"),
    _c("Zurich", "Switzerland", 47.3769, 8.5417, "Europe/Zurich"),
    _c("Stockholm", "Sweden", 59.3293, 18.0686, "Europe/Stockholm"),
    _c("Lisbon", "Portugal", 38.7223, -9.1393, "Europe/Lisbon"),
    _c("Dublin", "Ireland", 53.3498, -6.2603, "Europe/Dublin"),
    _c("Moscow", "Russia", 55.7558, 37.6173, "Europe/Moscow"),
    # --- Elsewhere ---
    _c("New York City", "United States", 40.7128, -74.0060, "America/New_York"),
    _c("Toronto", "Canada", 43.6532, -79.3832, "America/Toronto"),
    _c("Sydney", "Australia", -33.8688, 151.2093, "Australia/Sydney"),
    _c("Melbourne", "Australia", -37.8136, 144.9631, "Australia/Melbourne"),
    _c("Tokyo", "Japan", 35.6762, 139.6503, "Asia/Tokyo"),
    _c("Singapore", "Singapore", 1.3521, 103.8198, "Asia/Singapore"),
    _c("Dubai", "UAE", 25.2048, 55.2708, "Asia/Dubai"),
    _c("Cairo", "Egypt", 30.0444, 31.2357, "Africa/Cairo"),
    _c("Lagos", "Nigeria", 6.5244, 3.3792, "Africa/Lagos"),
    _c("Nairobi", "Kenya", -1.2921, 36.8219, "Africa/Nairobi"),
    _c("Johannesburg", "South Africa", -26.2041, 28.0473, "Africa/Johannesburg"),
    _c("Tel Aviv", "Israel", 32.0853, 34.7818, "Asia/Jerusalem"),
    _c("Istanbul", "Turkey", 41.0082, 28.9784, "Europe/Istanbul"),
    _c("Bangkok", "Thailand", 13.7563, 100.5018, "Asia/Bangkok"),
    _c("Jakarta", "Indonesia", -6.2088, 106.8456, "Asia/Jakarta"),
    _c("Buenos Aires", "Argentina", -34.6037, -58.3816, "America/Argentina/Buenos_Aires"),
    _c("Santiago", "Chile", -33.4489, -70.6693, "America/Santiago"),
    _c("Rio de Janeiro", "Brazil", -22.9068, -43.1729, "America/Sao_Paulo"),
    _c("Mexico City", "Mexico", 19.4326, -99.1332, "America/Mexico_City"),
    _c("Auckland", "New Zealand", -36.8485, 174.7633, "Pacific/Auckland"),
]

DEFAULT_TIMEZONE = "Asia/Kolkata"


def search(query: str, limit: int = 12) -> list[City]:
    """Case-insensitive match on city or country name."""
    q = query.strip().lower()
    if not q:
        return CITIES[:limit]
    exact = [c for c in CITIES if c.name.lower() == q]
    if exact:
        return exact[:limit]
    starts = [c for c in CITIES if c.name.lower().startswith(q)]
    contains = [c for c in CITIES if q in c.name.lower() or q in c.country.lower()]
    seen, out = set(), []
    for c in starts + contains:
        if c.name not in seen:
            seen.add(c.name)
            out.append(c)
        if len(out) >= limit:
            break
    return out


def get(name: str) -> City | None:
    for c in CITIES:
        if c.name.lower() == name.strip().lower():
            return c
    return None