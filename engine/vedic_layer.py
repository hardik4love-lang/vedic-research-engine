"""
Vedic Astrology Layer — Pure Python on top of Swiss Ephemeris

All Vedic calculations: sidereal conversion, nakshatras, dashas,
divisional charts, dignity, aspects, yogas.
"""

from dataclasses import dataclass, field
from datetime import datetime

from engine.swisseph_wrapper import (
    NAKSHATRA_NAMES,
    SIGN_NAMES,
    JulianDay,
    PlanetPosition,
    calc_all_planets,
    calc_ascendant,
    dasha_from_moon_nakshatra,
    degree_in_sign,
    julian_day_from_datetime,
    nakshatra_from_longitude,
    normalize_angle,
    sign_from_longitude,
    sub_dasha,
    tropical_to_sidereal,
)

# ============================================================================
# CORE DATA CLASSES
# ============================================================================

@dataclass
class VedicPlanet:
    """Planet with full Vedic attributes"""
    name: str
    longitude_sidereal: float      # 0-360 sidereal
    sign: int                      # 0-11
    degree_in_sign: float          # 0-30
    nakshatra: int                 # 1-27
    nakshatra_name: str
    pada: int                      # 1-4
    house: int                     # 1-12 (whole sign from Lagna)
    retrograde: bool
    combust: bool
    # exalted, moolatrikona, own, friendly, neutral, enemy, debilitated
    dignity: str
    latitude: float
    speed: float


@dataclass
class HouseInfo:
    """House with lord and planets"""
    number: int                    # 1-12
    sign: int                      # 0-11 (whole sign)
    sign_name: str
    lord: str                      # Planet name that owns this sign
    planets: list[str] = field(default_factory=list)
    lord_position: VedicPlanet | None = None


@dataclass
class DivisionalChart:
    """A divisional chart (varga)"""
    name: str                      # D1, D9, D10, D12
    division: int                  # 1, 9, 10, 12
    planets: dict[str, VedicPlanet]  # Planet name -> position in this varga
    lagna_sign: int
    houses: list[HouseInfo]


@dataclass
class DashaPeriod:
    """Vimshottari dasha period"""
    level: int                     # 1=Maha, 2=Antar, 3=Pratyantar
    lord: str
    start_date: datetime
    end_date: datetime
    start_jd: float
    end_jd: float
    sub_periods: list['DashaPeriod'] = field(default_factory=list)


@dataclass
class VedicChart:
    """Complete Vedic chart with all layers"""
    # Birth data
    birth_datetime: datetime
    birth_timezone: str
    latitude: float
    longitude: float
    julian_day: JulianDay
    
    # Calculation config snapshot
    ayanamsha: str = "lahiri"
    house_system: str = "whole_sign"
    
    # Core chart
    lagna_sign: int = 0
    lagna_degree: float = 0.0
    planets: dict[str, VedicPlanet] = field(default_factory=dict)
    houses: list[HouseInfo] = field(default_factory=list)
    
    # Divisional charts
    divisional_charts: dict[str, DivisionalChart] = field(default_factory=dict)
    
    # Dasha
    dasha_periods: list[DashaPeriod] = field(default_factory=list)
    
    # Yogas
    yogas: list[dict] = field(default_factory=list)
    
    # Config snapshot
    calc_config: dict = field(default_factory=dict)


# ============================================================================
# DIGNITY CALCULATIONS
# ============================================================================

# Exaltation degrees (sidereal)
EXALTATION = {
    "sun": (0, 10),       # Aries 10°
    "moon": (1, 3),       # Taurus 3°
    "mars": (9, 28),      # Capricorn 28°
    "mercury": (5, 15),   # Virgo 15°
    "jupiter": (3, 5),    # Cancer 5°
    "venus": (11, 27),    # Pisces 27°
    "saturn": (6, 20),    # Libra 20°
    "rahu": (1, 20),      # Taurus 20° (traditional)
    "ketu": (7, 20),      # Scorpio 20° (traditional)
}

# Debilitation degrees (sidereal)
DEBILITATION = {
    "sun": (6, 10),       # Libra 10°
    "moon": (7, 3),       # Scorpio 3°
    "mars": (3, 28),      # Cancer 28°
    "mercury": (11, 15),  # Pisces 15°
    "jupiter": (9, 5),    # Capricorn 5°
    "venus": (5, 27),     # Virgo 27°
    "saturn": (0, 20),    # Aries 20°
    "rahu": (7, 20),      # Scorpio 20°
    "ketu": (1, 20),      # Taurus 20°
}

# Moolatrikona ranges (sign, start_deg, end_deg)
MOOLATRIKONA = {
    "sun": (4, 0, 20),       # Leo 0-20
    "moon": (1, 3, 30),      # Taurus 3-30
    "mars": (0, 0, 12),      # Aries 0-12
    "mercury": (5, 15, 20),  # Virgo 15-20
    "jupiter": (8, 0, 10),   # Sagittarius 0-10
    "venus": (6, 0, 15),     # Libra 0-15
    "saturn": (10, 0, 20),   # Aquarius 0-20
}

# Own signs
OWN_SIGNS = {
    "sun": [4],              # Leo
    "moon": [3],             # Cancer
    "mars": [0, 7],          # Aries, Scorpio
    "mercury": [2, 5],       # Gemini, Virgo
    "jupiter": [8, 11],      # Sagittarius, Pisces
    "venus": [1, 6],         # Taurus, Libra
    "saturn": [9, 10],       # Capricorn, Aquarius
    "rahu": [],              # No own signs
    "ketu": [],              # No own signs
}

# Friend/Enemy/Neutral (simplified traditional)
FRIENDS = {
    "sun": ["moon", "mars", "jupiter"],
    "moon": ["sun", "mercury"],
    "mars": ["sun", "moon", "jupiter"],
    "mercury": ["sun", "venus"],
    "jupiter": ["sun", "moon", "mars"],
    "venus": ["mercury", "saturn"],
    "saturn": ["mercury", "venus"],
    "rahu": ["mercury", "venus", "saturn"],
    "ketu": ["mars", "saturn"],
}

ENEMIES = {
    "sun": ["venus", "saturn"],
    "moon": [],              # Moon has no enemies
    "mars": ["mercury"],
    "mercury": ["moon"],
    "jupiter": ["mercury", "venus"],
    "venus": ["sun", "moon"],
    "saturn": ["sun", "moon", "mars"],
    "rahu": ["sun", "moon", "mars", "jupiter"],
    "ketu": ["sun", "moon", "jupiter"],
}


def calculate_dignity(planet: str, sign: int, degree: float) -> str:
    """Calculate planetary dignity."""
    planet = planet.lower()
    
    # Check exaltation (within 3° of exact degree)
    if planet in EXALTATION:
        ex_sign, ex_deg = EXALTATION[planet]
        if sign == ex_sign and abs(degree - ex_deg) <= 3:
            return "exalted"
    
    # Check debilitation
    if planet in DEBILITATION:
        deb_sign, deb_deg = DEBILITATION[planet]
        if sign == deb_sign and abs(degree - deb_deg) <= 3:
            return "debilitated"
    
    # Check moolatrikona
    if planet in MOOLATRIKONA:
        mt_sign, mt_start, mt_end = MOOLATRIKONA[planet]
        if sign == mt_sign and mt_start <= degree <= mt_end:
            return "moolatrikona"
    
    # Check own sign
    if planet in OWN_SIGNS and sign in OWN_SIGNS[planet]:
        return "own"
    
    # Check friendly
    if planet in FRIENDS:
        # Get lord of the sign
        sign_lord = get_sign_lord(sign)
        if sign_lord in FRIENDS[planet]:
            return "friendly"
    
    # Check enemy
    if planet in ENEMIES:
        sign_lord = get_sign_lord(sign)
        if sign_lord in ENEMIES[planet]:
            return "enemy"
    
    return "neutral"


def get_sign_lord(sign: int) -> str:
    """Get the lord of a sign."""
    lords = [
        "mars",      # Aries
        "venus",     # Taurus
        "mercury",   # Gemini
        "moon",      # Cancer
        "sun",       # Leo
        "mercury",   # Virgo
        "venus",     # Libra
        "mars",      # Scorpio
        "jupiter",   # Sagittarius
        "saturn",    # Capricorn
        "saturn",    # Aquarius
        "jupiter",   # Pisces
    ]
    return lords[sign % 12]


# ============================================================================
# COMBUSTION CALCULATION
# ============================================================================

COMBUSTION_ORBS = {
    "moon": 12,
    "mars": 17,
    "mercury": 14,      # 12 if retrograde
    "jupiter": 11,
    "venus": 10,        # 8 if retrograde
    "saturn": 15,
    "rahu": 0,          # Nodes don't combust
    "ketu": 0,
}


def calculate_combustion(planet: str, planet_longitude: float, 
                         sun_longitude: float, retrograde: bool) -> bool:
    """Check if planet is combust (too close to Sun)."""
    if planet in ["rahu", "ketu", "sun"]:
        return False
    
    orb = COMBUSTION_ORBS.get(planet, 0)
    if orb == 0:
        return False
    
    # Adjust for retrograde
    if retrograde:
        if planet == "mercury":
            orb = 12
        elif planet == "venus":
            orb = 8
    
    # Angular distance
    diff = abs(planet_longitude - sun_longitude)
    diff = min(diff, 360 - diff)
    
    return diff <= orb


# ============================================================================
# ASPECTS (PARASHARA)
# ============================================================================

# Full aspects (100% strength)
FULL_ASPECTS = {
    "sun": [7],
    "moon": [7],
    "mars": [4, 7, 8],
    "mercury": [7],
    "jupiter": [5, 7, 9],
    "venus": [7],
    "saturn": [3, 7, 10],
    "rahu": [5, 7, 9],
    "ketu": [5, 7, 9],
}


def get_aspects(planet: str, from_house: int) -> list[int]:
    """Get houses aspected by planet from given house."""
    aspects = FULL_ASPECTS.get(planet, [7])
    result = []
    for a in aspects:
        target = (from_house + a - 1) % 12 + 1
        result.append(target)
    return result


def planet_aspects_house(planet: str, from_house: int, target_house: int) -> bool:
    """Check if planet aspects target house from from_house."""
    return target_house in get_aspects(planet, from_house)


# ============================================================================
# DIVISIONAL CHARTS
# ============================================================================

def calculate_divisional_longitude(longitude: float, division: int) -> float:
    """
    Calculate a planet's longitude in a divisional chart (varga).

    Parashara's rule: each sign is divided into `division` equal parts of
    30/division degrees. For odd divisions (D1, D9) the varga signs count
    forward from the rashi itself; for even divisions (D10, D12) they count
    backward. Example (D9): Taurus 0-3d20' -> Taurus, Taurus 3d20'-6d40' -> Gemini.
    """
    if division < 1:
        raise ValueError("division must be >= 1")
    if division == 1:
        return normalize_angle(longitude)

    sign = sign_from_longitude(longitude)
    deg_in_sign = degree_in_sign(longitude)

    part_size = 30.0 / division
    part = min(int(deg_in_sign // part_size), division - 1)

    # Odd vargas count forward, even vargas count backward
    new_sign = (sign + part) % 12 if division % 2 == 1 else (sign - part) % 12

    # Degree carried into the varga sign, scaled back to a full sign
    new_deg = (deg_in_sign - part * part_size) * division

    return normalize_angle(new_sign * 30 + new_deg)


def build_divisional_chart(chart: VedicChart, division: int) -> DivisionalChart:
    """Build a divisional chart from the main chart."""
    div_name = f"D{division}"
    
    planets = {}
    for name, vp in chart.planets.items():
        new_lon = calculate_divisional_longitude(vp.longitude_sidereal, division)
        new_sign = sign_from_longitude(new_lon)
        new_deg = degree_in_sign(new_lon)
        new_nak, new_pada = nakshatra_from_longitude(new_lon)
        
        planets[name] = VedicPlanet(
            name=name,
            longitude_sidereal=new_lon,
            sign=new_sign,
            degree_in_sign=new_deg,
            nakshatra=new_nak,
            nakshatra_name=NAKSHATRA_NAMES[new_nak - 1],
            pada=new_pada,
            house=1,  # Will be recalculated based on divisional lagna
            retrograde=vp.retrograde,
            combust=False,  # Combustion not typically checked in vargas
            dignity=calculate_dignity(name, new_sign, new_deg),
            latitude=vp.latitude,
            speed=vp.speed
        )
    
    # Calculate divisional lagna
    lagna_lon = calculate_divisional_longitude(chart.lagna_degree, division)
    lagna_sign = sign_from_longitude(lagna_lon)
    
    # Build houses for this divisional chart
    houses = []
    for h in range(1, 13):
        h_sign = (lagna_sign + h - 1) % 12
        h_lord = get_sign_lord(h_sign)
        h_planets = [name for name, vp in planets.items() if vp.sign == h_sign]
        
        houses.append(HouseInfo(
            number=h,
            sign=h_sign,
            sign_name=SIGN_NAMES[h_sign],
            lord=h_lord,
            planets=h_planets
        ))
    
    return DivisionalChart(
        name=div_name,
        division=division,
        planets=planets,
        lagna_sign=lagna_sign,
        houses=houses
    )


# ============================================================================
# YOGAS
# ============================================================================

def detect_yogas(chart: VedicChart) -> list[dict]:
    """Detect core yogas in the chart."""
    yogas = []
    planets = chart.planets
    
    # Helper
    def get_planet(name: str) -> VedicPlanet | None:
        return planets.get(name.lower())
    
    def in_same_house(p1: str, p2: str) -> bool:
        vp1 = get_planet(p1)
        vp2 = get_planet(p2)
        return vp1 and vp2 and vp1.house == vp2.house
    
    def in_kendra(p: str) -> bool:
        vp = get_planet(p)
        return vp and vp.house in [1, 4, 7, 10]
    
    def in_kona(p: str) -> bool:
        vp = get_planet(p)
        return vp and vp.house in [1, 5, 9]
    
    # Gaja Kesari: Jupiter in kendra from Moon
    moon = get_planet("moon")
    jupiter = get_planet("jupiter")
    if moon and jupiter:
        moon_house = moon.house
        jupiter_from_moon = (jupiter.house - moon_house) % 12
        if jupiter_from_moon in [0, 3, 6, 9]:  # 1st, 4th, 7th, 10th from Moon
            yogas.append({
                "name": "Gaja Kesari Yoga",
                "type": "raja",
                "description": "Jupiter in kendra from Moon",
                "planets": ["moon", "jupiter"]
            })
    
    # Chandra-Mangala: Moon-Mars conjunction
    if in_same_house("moon", "mars"):
        yogas.append({
            "name": "Chandra-Mangala Yoga",
            "type": "wealth",
            "description": "Moon and Mars in same house",
            "planets": ["moon", "mars"]
        })
    
    # Kemadruma: Moon isolated
    if moon:
        moon_house = moon.house
        house_2 = (moon_house % 12) + 1
        house_12 = (moon_house - 2) % 12 + 1
        planets_2 = [p for p, vp in planets.items() if vp.house == house_2]
        planets_12 = [p for p, vp in planets.items() if vp.house == house_12]
        if not planets_2 and not planets_12:
            yogas.append({
                "name": "Kemadruma Yoga",
                "type": "malefic",
                "description": "Moon isolated - no planets in 2nd or 12th from Moon",
                "planets": ["moon"]
            })
    
    # Pancha Mahapurusha Yogas
    mahapurusha = {
        "mars": "Ruchaka",
        "mercury": "Bhadra",
        "jupiter": "Hamsa",
        "venus": "Malavya",
        "saturn": "Sasha"
    }
    for planet, yoga_name in mahapurusha.items():
        vp = get_planet(planet)
        if vp and vp.house in [1, 4, 7, 10] and vp.dignity in ["exalted", "own"]:
            yogas.append({
                "name": f"{yoga_name} Yoga",
                "type": "mahapurusha",
                "description": f"{planet.capitalize()} in own/exalted sign in kendra",
                "planets": [planet]
            })
    
    # Raja Yoga: Kendra-Kona lord associations
    # Lords of kendras (1,4,7,10) and konas (1,5,9)
    kendra_lords = set()
    kona_lords = set()
    for h in [1, 4, 7, 10]:
        sign = (chart.lagna_sign + h - 1) % 12
        kendra_lords.add(get_sign_lord(sign))
    for h in [1, 5, 9]:
        sign = (chart.lagna_sign + h - 1) % 12
        kona_lords.add(get_sign_lord(sign))
    
    # Check associations between kendra and kona lords
    for kl in kendra_lords:
        for kol in kona_lords:
            if kl != kol:
                # Check conjunction, mutual aspect, or exchange
                vp_kl = get_planet(kl)
                vp_kol = get_planet(kol)
                if vp_kl and vp_kol:
                    if vp_kl.house == vp_kol.house:
                        yogas.append({
                            "name": "Raja Yoga (Conjunction)",
                            "type": "raja",
                            "description": f"Kendra lord {kl} conjunct kona lord {kol}",
                            "planets": [kl, kol]
                        })
                    elif planet_aspects_house(kl, vp_kl.house, vp_kol.house) and \
                         planet_aspects_house(kol, vp_kol.house, vp_kl.house):
                        yogas.append({
                            "name": "Raja Yoga (Mutual Aspect)",
                            "type": "raja",
                            "description": f"Kendra lord {kl} and kona lord {kol} mutually aspect",
                            "planets": [kl, kol]
                        })
    
    # Dhana Yoga: 2nd/11th lord associations
    house_2_lord = get_sign_lord((chart.lagna_sign + 1) % 12)
    house_11_lord = get_sign_lord((chart.lagna_sign + 10) % 12)
    
    for lord in [house_2_lord, house_11_lord]:
        for other in [house_2_lord, house_11_lord, "jupiter", "venus"]:
            if lord != other:
                vp_lord = get_planet(lord)
                vp_other = get_planet(other)
                if vp_lord and vp_other:
                    if vp_lord.house == vp_other.house or \
                       planet_aspects_house(lord, vp_lord.house, vp_other.house):
                        yogas.append({
                            "name": "Dhana Yoga",
                            "type": "wealth",
                            "description": f"Wealth yoga: {lord} with {other}",
                            "planets": [lord, other]
                        })
    
    return yogas


# ============================================================================
# MAIN CHART BUILDER
# ============================================================================

def build_vedic_chart(
    birth_datetime: datetime,
    birth_timezone: str,
    latitude: float,
    longitude: float,
    ayanamsha: str = "lahiri",
    divisional_charts: list[int] = None
) -> VedicChart:
    """
    Build complete Vedic chart from birth data.
    
    Args:
        birth_datetime: Naive datetime in birth timezone
        birth_timezone: IANA timezone
        latitude: WGS84 latitude
        longitude: WGS84 longitude
        ayanamsha: Ayanamsha name
        divisional_charts: List of divisions to compute (default: [1, 9, 10, 12])
    
    Returns:
        Complete VedicChart object
    """
    if divisional_charts is None:
        divisional_charts = [1, 9, 10, 12]
    
    # Julian day
    jd = julian_day_from_datetime(birth_datetime, birth_timezone)
    
    # Calculate planets (tropical)
    tropical_planets = calc_all_planets(jd.jd_tt)
    
    # Convert to sidereal
    sidereal_planets = {}
    for name, tp in tropical_planets.items():
        sid_lon = tropical_to_sidereal(tp.longitude_tropical, jd.jd_tt, ayanamsha)
        sidereal_planets[name] = PlanetPosition(
            planet=name,
            longitude_tropical=tp.longitude_tropical,
            latitude=tp.latitude,
            distance=tp.distance,
            speed_longitude=tp.speed_longitude,
            speed_latitude=tp.speed_latitude,
            speed_distance=tp.speed_distance,
            retrograde=tp.retrograde
        )
        # Override with sidereal longitude
        sidereal_planets[name].longitude_tropical = sid_lon
    
    # Ascendant
    asc_tropical = calc_ascendant(jd.jd_tt, latitude, longitude)
    asc_sidereal = tropical_to_sidereal(asc_tropical, jd.jd_tt, ayanamsha)
    lagna_sign = sign_from_longitude(asc_sidereal)
    
    # Build Vedic planets
    vedic_planets = {}
    sun_lon = sidereal_planets["sun"].longitude_tropical
    
    for name, sp in sidereal_planets.items():
        lon = sp.longitude_tropical
        sign = sign_from_longitude(lon)
        deg = degree_in_sign(lon)
        nak, pada = nakshatra_from_longitude(lon)
        
        # House (whole sign from Lagna)
        house = ((sign - lagna_sign) % 12) + 1
        
        # Combustion
        combust = calculate_combustion(name, lon, sun_lon, sp.retrograde)
        
        # Dignity
        dignity = calculate_dignity(name, sign, deg)
        
        vedic_planets[name] = VedicPlanet(
            name=name,
            longitude_sidereal=lon,
            sign=sign,
            degree_in_sign=deg,
            nakshatra=nak,
            nakshatra_name=NAKSHATRA_NAMES[nak - 1],
            pada=pada,
            house=house,
            retrograde=sp.retrograde,
            combust=combust,
            dignity=dignity,
            latitude=sp.latitude,
            speed=sp.speed_longitude
        )
    
    # Build houses
    houses = []
    for h in range(1, 13):
        h_sign = (lagna_sign + h - 1) % 12
        h_lord = get_sign_lord(h_sign)
        h_planets = [name for name, vp in vedic_planets.items() if vp.house == h]
        h_lord_planet = vedic_planets.get(h_lord)
        
        houses.append(HouseInfo(
            number=h,
            sign=h_sign,
            sign_name=SIGN_NAMES[h_sign],
            lord=h_lord,
            planets=h_planets,
            lord_position=h_lord_planet
        ))
    
    # Create chart object
    chart = VedicChart(
        birth_datetime=birth_datetime,
        birth_timezone=birth_timezone,
        latitude=latitude,
        longitude=longitude,
        julian_day=jd,
        ayanamsha=ayanamsha,
        house_system="whole_sign",
        lagna_sign=lagna_sign,
        lagna_degree=asc_sidereal,
        planets=vedic_planets,
        houses=houses,
        calc_config={
            "ayanamsha": ayanamsha,
            "house_system": "whole_sign",
            "divisional_charts": [f"D{d}" for d in divisional_charts],
            "dasha_system": "vimshottari",
            "dasha_levels": 3,
        }
    )
    
    # Build divisional charts
    for div in divisional_charts:
        if div == 1:
            chart.divisional_charts["D1"] = DivisionalChart(
                name="D1",
                division=1,
                planets=vedic_planets,
                lagna_sign=lagna_sign,
                houses=houses
            )
        else:
            chart.divisional_charts[f"D{div}"] = build_divisional_chart(chart, div)
    
    # Calculate dasha
    moon = vedic_planets.get("moon")
    if moon:
        dashas = dasha_from_moon_nakshatra(moon.longitude_sidereal, jd.jd_tt)
        chart.dasha_periods = convert_dashas_to_periods(dashas)
        
        # Add sub-dashas (2 levels)
        for maha in chart.dasha_periods:
            maha.sub_periods = convert_dashas_to_periods(
                sub_dasha(maha.lord, maha.start_jd, maha.end_jd, level=2)
            )
            for antar in maha.sub_periods:
                antar.sub_periods = convert_dashas_to_periods(
                    sub_dasha(antar.lord, antar.start_jd, antar.end_jd, level=3)
                )
    
    # Detect yogas
    chart.yogas = detect_yogas(chart)
    
    return chart


def convert_dashas_to_periods(dashas: list[dict]) -> list[DashaPeriod]:
    """Convert raw dasha dicts to DashaPeriod objects."""
    from engine.swisseph_wrapper import swe
    periods = []
    for d in dashas:
        # Convert JD to datetime
        def jd_to_dt(jd_val):
            y, m, d, h = swe.revjul(jd_val)
            return datetime(int(y), int(m), int(d), int(h), int((h%1)*60), int(((h%1)*60%1)*60))
        
        periods.append(DashaPeriod(
            level=d["level"],
            lord=d["lord"],
            start_date=jd_to_dt(d["start_jd"]),
            end_date=jd_to_dt(d["end_jd"]),
            start_jd=d["start_jd"],
            end_jd=d["end_jd"]
        ))
    return periods


# ============================================================================
# TRANSITS
# ============================================================================

@dataclass
class Transit:
    """Planetary transit event"""
    planet: str
    # ingress, retrograde_start, retrograde_end,
    # combustion_start, combustion_end
    event_type: str
    from_sign: int
    to_sign: int
    date: datetime
    exact_longitude: float


def calculate_transits(
    chart: VedicChart,
    start_date: datetime,
    end_date: datetime,
    planets: list[str] = None
) -> list[Transit]:
    """
    Calculate planetary transits over a date range.
    
    Returns list of transit events.
    """
    if planets is None:
        planets = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"]
    
    transits = []
    
    # For each planet, step through time and detect sign changes
    # Simplified: check daily
    current = start_date
    prev_signs = {}
    
    # Get initial positions
    jd_start = julian_day_from_datetime(current, chart.birth_timezone)
    initial = calc_all_planets(jd_start.jd_tt)
    for p in planets:
        lon = tropical_to_sidereal(initial[p].longitude_tropical, jd_start.jd_tt, chart.ayanamsha)
        prev_signs[p] = sign_from_longitude(lon)
    
    # Step through days
    delta_days = (end_date - start_date).days
    for day_offset in range(delta_days + 1):
        check_date = start_date.replace(hour=12, minute=0, second=0, microsecond=0)
        check_date = check_date.replace(day=start_date.day + day_offset)
        if check_date > end_date:
            break
        
        jd = julian_day_from_datetime(check_date, chart.birth_timezone)
        positions = calc_all_planets(jd.jd_tt)
        
        for p in planets:
            lon = tropical_to_sidereal(positions[p].longitude_tropical, jd.jd_tt, chart.ayanamsha)
            sign = sign_from_longitude(lon)
            
            if p in prev_signs and sign != prev_signs[p]:
                transits.append(Transit(
                    planet=p,
                    event_type="ingress",
                    from_sign=prev_signs[p],
                    to_sign=sign,
                    date=check_date,
                    exact_longitude=lon
                ))
            prev_signs[p] = sign
    
    return transits


# ============================================================================
# HOUSE LORD RELATIONSHIPS
# ============================================================================

def analyze_house_lords(chart: VedicChart) -> dict:
    """Analyze relationships between house lords."""
    relationships = {}
    
    for h in range(1, 13):
        h_lord = chart.houses[h - 1].lord
        lord_planet = chart.planets.get(h_lord)
        
        if lord_planet:
            relationships[h] = {
                "lord": h_lord,
                "lord_house": lord_planet.house,
                "lord_sign": lord_planet.sign,
                "lord_dignity": lord_planet.dignity,
                "lord_retrograde": lord_planet.retrograde,
                "lord_combust": lord_planet.combust,
                "house_of_lord_from_house": (lord_planet.house - h) % 12 + 1,
                "aspects_own_house": planet_aspects_house(h_lord, lord_planet.house, h),
            }
    
    return relationships


# ============================================================================
# CHART SERIALIZATION
# ============================================================================

def chart_to_dict(chart: VedicChart) -> dict:
    """Serialize chart to JSON-compatible dict."""
    return {
        "birth_data": {
            "datetime": chart.birth_datetime.isoformat(),
            "timezone": chart.birth_timezone,
            "latitude": chart.latitude,
            "longitude": chart.longitude,
        },
        "calc_config": chart.calc_config,
        "lagna": {
            "sign": chart.lagna_sign,
            "sign_name": SIGN_NAMES[chart.lagna_sign],
            "degree": chart.lagna_degree,
        },
        "planets": {
            name: {
                "longitude": vp.longitude_sidereal,
                "sign": vp.sign,
                "sign_name": SIGN_NAMES[vp.sign],
                "degree": vp.degree_in_sign,
                "nakshatra": vp.nakshatra,
                "nakshatra_name": vp.nakshatra_name,
                "pada": vp.pada,
                "house": vp.house,
                "retrograde": vp.retrograde,
                "combust": vp.combust,
                "dignity": vp.dignity,
            }
            for name, vp in chart.planets.items()
        },
        "houses": [
            {
                "number": h.number,
                "sign": h.sign,
                "sign_name": h.sign_name,
                "lord": h.lord,
                "planets": h.planets,
            }
            for h in chart.houses
        ],
        "divisional_charts": {
            name: {
                "division": dc.division,
                "lagna_sign": dc.lagna_sign,
                "planets": {
                    p: {
                        "sign": vp.sign,
                        "degree": vp.degree_in_sign,
                        "house": vp.house,
                    }
                    for p, vp in dc.planets.items()
                },
                "houses": [
                    {"number": h.number, "sign": h.sign, "lord": h.lord, "planets": h.planets}
                    for h in dc.houses
                ]
            }
            for name, dc in chart.divisional_charts.items()
        },
        "dasha": [
            {
                "level": d.level,
                "lord": d.lord,
                "start": d.start_date.isoformat(),
                "end": d.end_date.isoformat(),
                "sub_periods": [
                    {
                        "level": sp.level,
                        "lord": sp.lord,
                        "start": jd_to_dt(sp.start_jd).isoformat(),
                        "end": jd_to_dt(sp.end_jd).isoformat(),
                    }
                    for sp in d.sub_periods
                ] if hasattr(d, 'sub_periods') else []
            }
            for d in chart.dasha_periods
        ],
        "yogas": chart.yogas,
        "house_lords": analyze_house_lords(chart),
    }


def jd_to_dt(jd_val: float) -> datetime:
    from engine.swisseph_wrapper import swe
    y, m, d, h = swe.revjul(jd_val)
    return datetime(int(y), int(m), int(d), int(h), int((h%1)*60), int(((h%1)*60%1)*60))