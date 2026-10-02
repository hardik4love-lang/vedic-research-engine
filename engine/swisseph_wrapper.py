"""
Swiss Ephemeris Wrapper — Thin Layer for Vedic Calculations

Provides raw astronomical data. No Vedic logic here.
All angles returned in tropical coordinates; sidereal conversion applied upstream.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

# Planet constants mapping to Swiss Ephemeris
PLANET_MAP = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mars": swe.MARS,
    "mercury": swe.MERCURY,
    "jupiter": swe.JUPITER,
    "venus": swe.VENUS,
    "saturn": swe.SATURN,
    "rahu": swe.MEAN_NODE,      # Mean North Node
    "ketu": None,               # Calculated as opposite of Rahu
}

# Sign names (0 = Aries)
SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# Nakshatra names (1-27, starting at Ashwini = 0° Aries sidereal)
NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

# Nakshatra lords (Vimshottari sequence, 27 nakshatras)
# Ketu(Ash), Venus(Bha), Sun(Kri), Moon(Roh), Mars(Mri), Rahu(Ard),
# Jupiter(Pun), Saturn(Pus), Mercury(Ashlesha) ... repeats
NAKSHATRA_LORDS = [
    "ketu", "venus", "sun", "moon", "mars", "rahu", "jupiter", "saturn", "mercury",  # 1-9
    "ketu", "venus", "sun", "moon", "mars", "rahu", "jupiter", "saturn", "mercury",  # 10-18
    "ketu", "venus", "sun", "moon", "mars", "rahu", "jupiter", "saturn",             # 19-26
    "mercury",                                                                       # 27 Revati
]

# Vimshottari dasha periods (years)
DASHA_PERIODS = {
    "ketu": 7,
    "venus": 20,
    "sun": 6,
    "moon": 10,
    "mars": 7,
    "rahu": 18,
    "jupiter": 16,
    "saturn": 19,
    "mercury": 17
}

DASHA_SEQUENCE = ["ketu", "venus", "sun", "moon", "mars", "rahu", "jupiter", "saturn", "mercury"]

# Ayanamsha name -> Swiss Ephemeris constant
AYANAMSHA_MAP = {
    "lahiri": swe.SIDM_LAHIRI,
    "raman": swe.SIDM_RAMAN,
    "krishnamurti": swe.SIDM_KRISHNAMURTI,
    "fagan_bradley": swe.SIDM_FAGAN_BRADLEY,
    "aryabhata": swe.SIDM_ARYABHATA,
}


@dataclass
class PlanetPosition:
    """Raw planetary position from Swiss Ephemeris"""
    planet: str
    longitude_tropical: float      # 0-360, tropical
    latitude: float                # Ecliptic latitude
    distance: float                # AU
    speed_longitude: float         # Degrees/day
    speed_latitude: float
    speed_distance: float
    retrograde: bool               # speed_longitude < 0


@dataclass
class HouseCusps:
    """House cusps from Swiss Ephemeris"""
    cusps: list[float]             # 13 elements (0 unused, 1-12)
    ascmc: list[float]             # [ASC, MC, ARMC, Vertex, EquAsc, CoAsc, PolAsc]


@dataclass
class JulianDay:
    """Julian Day with timezone info"""
    jd_ut: float                   # Universal Time
    jd_tt: float                   # Terrestrial Time
    timezone_str: str              # IANA timezone
    utc_offset_hours: float        # Hours from UTC at this moment


def set_ephemeris_path(path: str | None = None):
    """Set Swiss Ephemeris data file path. Uses built-in if None."""
    if path:
        swe.set_ephe_path(path)
    else:
        # Use built-in Moshier ephemeris (lower precision, no files needed)
        swe.set_ephe_path("")


def _tzinfo(tz_str: str):
    """Resolve a timezone string to a tzinfo.

    Accepts IANA names ("Asia/Kolkata") and fixed offsets written as
    "UTC+05:30" or "+05:30". The fixed-offset form matters for historical
    births: Etc/GMT zones only exist at whole hours, so IST's +05:30 cannot
    be expressed that way, and an explicit offset is the only honest way to
    record a local mean time.
    """
    s = (tz_str or "").strip()
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d{1,2}):?(\d{2})", s, re.IGNORECASE)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        minutes = sign * (int(m.group(2)) * 60 + int(m.group(3)))
        return UTC if minutes == 0 else timezone(timedelta(minutes=minutes))
    return ZoneInfo(s)


def julian_day_from_datetime(dt: datetime, tz_str: str) -> JulianDay:
    """
    Convert a local civil datetime to Julian Day.

    Args:
        dt: Naive or aware datetime (interpreted as local time in tz_str)
        tz_str: IANA timezone identifier

    Returns:
        JulianDay with UT and TT

    Uses stdlib zoneinfo (IANA tzdata). pytz is deliberately NOT used: its
    localize() returns Local Mean Time for pre-standard-time dates, which
    disagrees with the IANA database by up to ~32 minutes for some zones
    (e.g. Asia/Kolkata before 1906, America/New_York before 1918). An error
    of that size moves the ascendant by several degrees and can change the
    whole-sign house assignment.
    """
    tz = _tzinfo(tz_str)

    if dt.tzinfo is None:
        dt_local = dt.replace(tzinfo=tz)
    else:
        dt_local = dt.astimezone(tz)
    
    # Convert to UTC
    dt_utc = dt_local.astimezone(UTC)
    
    # Julian Day UT
    hour = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600 + dt_utc.microsecond/3_600_000
    jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour)
    
    # Delta T for Terrestrial Time
    delta_t = swe.deltat(jd_ut)
    jd_tt = jd_ut + delta_t / 86400.0
    
    # UTC offset at this moment (hours)
    utc_offset = dt_local.utcoffset().total_seconds() / 3600
    
    return JulianDay(
        jd_ut=jd_ut,
        jd_tt=jd_tt,
        timezone_str=tz_str,
        utc_offset_hours=utc_offset
    )


def calc_planet(jd_tt: float, planet: str, flags: int = swe.FLG_SWIEPH) -> PlanetPosition:
    """
    Calculate planet position using Swiss Ephemeris.

    FLG_SPEED is always applied: without it swisseph returns speed 0.0 for
    every body, which would silently break retrograde detection.

    Args:
        jd_tt: Julian Day Terrestrial Time
        planet: Planet key from PLANET_MAP
        flags: Swiss Ephemeris flags
    
    Returns:
        PlanetPosition with tropical coordinates
    """
    if planet not in PLANET_MAP:
        raise ValueError(f"Unknown planet: {planet}")
    
    swe_planet = PLANET_MAP[planet]
    
    if planet == "ketu":
        # Ketu is opposite Rahu (mean node)
        rahu_pos = calc_planet(jd_tt, "rahu", flags)
        return PlanetPosition(
            planet="ketu",
            longitude_tropical=normalize_angle(rahu_pos.longitude_tropical + 180),
            latitude=-rahu_pos.latitude,
            distance=rahu_pos.distance,
            speed_longitude=rahu_pos.speed_longitude,
            speed_latitude=-rahu_pos.speed_latitude,
            speed_distance=rahu_pos.speed_distance,
            retrograde=True  # Ketu always retrograde (mean node)
        )
    
    # Calculate. FLG_SPEED is mandatory for correct retrograde detection.
    # Fall back to the built-in Moshier ephemeris when the Swiss Ephemeris
    # data files are absent or the date is outside their range.
    try:
        result, _ = swe.calc_ut(jd_tt, swe_planet, flags | swe.FLG_SPEED)
    except swe.Error:
        result, _ = swe.calc_ut(jd_tt, swe_planet, swe.FLG_MOSEPH | swe.FLG_SPEED)
    
    # result = [longitude, latitude, distance, speed_lon, speed_lat, speed_dist]
    longitude = normalize_angle(result[0])
    speed_lon = result[3]
    
    return PlanetPosition(
        planet=planet,
        longitude_tropical=longitude,
        latitude=result[1],
        distance=result[2],
        speed_longitude=speed_lon,
        speed_latitude=result[4],
        speed_distance=result[5],
        retrograde=speed_lon < 0
    )


def calc_all_planets(jd_tt: float, flags: int = swe.FLG_SWIEPH) -> dict[str, PlanetPosition]:
    """Calculate all 9 Vedic planets."""
    return {
        name: calc_planet(jd_tt, name, flags)
        for name in PLANET_MAP.keys()
    }


def calc_houses(jd_tt: float, latitude: float, longitude: float, 
                house_system: bytes = b'W') -> HouseCusps:
    """
    Calculate house cusps.
    
    Args:
        jd_tt: Julian Day TT
        latitude: Geographic latitude
        longitude: Geographic longitude
        house_system: House system (b'W'=Whole Sign, b'P'=Placidus, etc.)
    
    Returns:
        HouseCusps with 12 cusps + ASC/MC
    """
    cusps, ascmc = swe.houses(jd_tt, latitude, longitude, house_system)
    # cusps[0] is unused, cusps[1..12] are house cusps
    return HouseCusps(
        cusps=list(cusps),
        ascmc=list(ascmc)
    )


def calc_ascendant(jd_tt: float, latitude: float, longitude: float) -> float:
    """Calculate Ascendant (Lagna) longitude."""
    houses = calc_houses(jd_tt, latitude, longitude, b'W')  # Whole sign uses ASC for 1st house
    return normalize_angle(houses.ascmc[0])  # ASC is first element


def calc_midheaven(jd_tt: float, latitude: float, longitude: float) -> float:
    """Calculate Midheaven (MC) longitude."""
    houses = calc_houses(jd_tt, latitude, longitude, b'W')
    return normalize_angle(houses.ascmc[1])  # MC is second element


def normalize_angle(angle: float) -> float:
    """Normalize angle to 0-360 degrees."""
    return angle % 360.0


def tropical_to_sidereal(longitude_tropical: float, jd_tt: float, 
                         ayanamsha: str = "lahiri") -> float:
    """
    Convert tropical longitude to sidereal by subtracting the ayanamsha.
    
    Args:
        longitude_tropical: 0-360 tropical
        jd_tt: Julian Day TT
        ayanamsha: Ayanamsha name (lahiri, raman, krishnamurti, etc.)
    
    Returns:
        Sidereal longitude 0-360
    """
    ayanamsa = get_ayanamsha_value(jd_tt, ayanamsha)
    return normalize_angle(longitude_tropical - ayanamsa)


def get_ayanamsha_value(jd_tt: float, ayanamsha: str = "lahiri") -> float:
    """Get ayanamsha value in degrees for given date."""
    if ayanamsha not in AYANAMSHA_MAP:
        raise ValueError(f"Unknown ayanamsha: {ayanamsha}")
    swe.set_sid_mode(AYANAMSHA_MAP[ayanamsha], 0, 0)
    return swe.get_ayanamsa_ut(jd_tt)


def sign_from_longitude(longitude: float) -> int:
    """Get sign index (0-11) from longitude."""
    return int(longitude // 30) % 12


def degree_in_sign(longitude: float) -> float:
    """Get degree within sign (0-30)."""
    return longitude % 30.0


def nakshatra_from_longitude(longitude_sidereal: float) -> tuple[int, int]:
    """
    Get nakshatra (1-27) and pada (1-4) from sidereal longitude.
    
    Returns:
        (nakshatra_index_1_based, pada_1_based)
    """
    # Each nakshatra = 13°20' = 13.333...°
    # Each pada = 3°20' = 3.333...°
    nakshatra_span = 360.0 / 27  # 13.333...
    pada_span = nakshatra_span / 4  # 3.333...
    
    nakshatra_idx = int(longitude_sidereal // nakshatra_span) % 27
    pada_idx = int((longitude_sidereal % nakshatra_span) // pada_span) % 4
    
    return nakshatra_idx + 1, pada_idx + 1  # 1-based


def dasha_from_moon_nakshatra(moon_longitude_sidereal: float, 
                               birth_jd_tt: float) -> list[dict]:
    """
    Calculate Vimshottari dasha periods from Moon's nakshatra.
    
    Returns list of dasha periods with start/end Julian days.
    """
    nakshatra_idx, pada = nakshatra_from_longitude(moon_longitude_sidereal)
    # nakshatra_idx is 1-based, convert to 0-based for array
    lord = NAKSHATRA_LORDS[nakshatra_idx - 1]
    
    # Find starting position in dasha sequence
    start_idx = DASHA_SEQUENCE.index(lord)
    
    # Calculate elapsed portion of first dasha
    # Moon's position within nakshatra determines how much of first dasha has passed
    nakshatra_span = 360.0 / 27
    nakshatra_start = (nakshatra_idx - 1) * nakshatra_span
    moon_in_nakshatra = moon_longitude_sidereal - nakshatra_start
    elapsed_fraction = moon_in_nakshatra / nakshatra_span
    
    dashas = []
    current_jd = birth_jd_tt
    
    # First dasha (partial)
    first_lord = DASHA_SEQUENCE[start_idx]
    first_total_years = DASHA_PERIODS[first_lord]
    first_remaining_years = first_total_years * (1 - elapsed_fraction)
    
    dashas.append({
        "lord": first_lord,
        "start_jd": current_jd,
        "end_jd": current_jd + first_remaining_years * 365.25,
        "total_years": first_total_years,
        "elapsed_years": first_total_years * elapsed_fraction,
        "remaining_years": first_remaining_years,
        "level": 1
    })
    current_jd = dashas[-1]["end_jd"]
    
    # Remaining dashas in sequence
    for i in range(1, 9):
        idx = (start_idx + i) % 9
        lord = DASHA_SEQUENCE[idx]
        years = DASHA_PERIODS[lord]
        dashas.append({
            "lord": lord,
            "start_jd": current_jd,
            "end_jd": current_jd + years * 365.25,
            "total_years": years,
            "elapsed_years": 0,
            "remaining_years": years,
            "level": 1
        })
        current_jd = dashas[-1]["end_jd"]
    
    return dashas


def sub_dasha(dasha_lord: str, dasha_start_jd: float, dasha_end_jd: float,
              level: int = 2) -> list[dict]:
    """
    Calculate sub-dasha (antardasha/pratyantardasha) periods within a dasha.
    
    Args:
        dasha_lord: Major dasha lord
        dasha_start_jd: Start JD of major dasha
        dasha_end_jd: End JD of major dasha
        level: 2=antardasha, 3=pratyantardasha
    
    Returns:
        List of sub-dasha periods
    """
    # Sequence starts with the major dasha lord
    start_idx = DASHA_SEQUENCE.index(dasha_lord)
    total_days = dasha_end_jd - dasha_start_jd
    
    sub_dashas = []
    current_jd = dasha_start_jd
    
    for i in range(9):
        idx = (start_idx + i) % 9
        sub_lord = DASHA_SEQUENCE[idx]
        sub_years = DASHA_PERIODS[sub_lord]
        
        # Proportional duration
        if level == 2:
            # Antardasha: (sub_years / 120) * major_years
            proportion = sub_years / 120.0
        elif level == 3:
            # Pratyantardasha: (sub_years / 120) * (major_years / 120) * 120
            # Simplified: proportional to sub_years within major dasha
            proportion = sub_years / 120.0
        else:
            proportion = sub_years / 120.0
        
        sub_days = total_days * proportion
        
        sub_dashas.append({
            "lord": sub_lord,
            "start_jd": current_jd,
            "end_jd": current_jd + sub_days,
            "level": level
        })
        current_jd += sub_days
    
    return sub_dashas