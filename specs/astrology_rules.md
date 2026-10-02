# Vedic Astrology Calculation Specification (MVP)

## Frozen Rules for MVP

### Zodiac & Ayanamsha
- **Zodiac**: Sidereal
- **Ayanamsha**: Lahiri (Chitrapaksha)
- **Reference epoch**: J2000.0
- **Precision**: Calculate to 0.01" (0.000002777... degrees)

### House System
- **Primary**: Whole Sign Houses (each sign = one house)
- **Lagna**: Ascendant degree determines 1st house cusp
- **Bhava cusps**: For reference only, not primary house determination

### Planets (Grahas)
| Planet | Sanskrit | Symbol | Notes |
|--------|----------|--------|-------|
| Sun | Surya | ☉ | |
| Moon | Chandra | ☽ | |
| Mars | Mangala | ♂ | |
| Mercury | Budha | ☿ | |
| Jupiter | Guru | ♃ | |
| Venus | Shukra | ♀ | |
| Saturn | Shani | ♄ | |
| Rahu | Rahu | ☊ | North Node (mean) |
| Ketu | Ketu | ☋ | South Node (mean, opposite Rahu) |

**Excluded from MVP**: Uranus, Neptune, Pluto, asteroids, fixed stars

### Nakshatras (27)
- Span: 13°20' each (360°/27)
- Starting point: Ashwini at 0° Aries (sidereal)
- Pada: 4 per nakshatra (3°20' each)

### Divisional Charts (Vargas) — MVP Set
1. **D1 (Rashi)** — Main chart
2. **D9 (Navamsa)** — Spouse, dharma, fruits of karma
3. **D10 (Dashamsa)** — Career, profession
4. **D12 (Dwadashamsa)** — Parents, lineage

### Vimshottari Dasha
- **Cycle**: 120 years
- **Sequence**: Ketu (7) → Venus (20) → Sun (6) → Moon (10) → Mars (7) → Rahu (18) → Jupiter (16) → Saturn (19) → Mercury (17)
- **Sub-periods**: Antardasha, Pratyantardasha, Sookshma, Prana (MVP: Dasha + Antardasha + Pratyantardasha)
- **Starting point**: Moon's nakshatra at birth

### Planetary Dignity
| Planet | Exaltation | Debilitation | Moolatrikona | Own Signs |
|--------|------------|--------------|--------------|-----------|
| Sun | Aries 10° | Libra 10° | Leo 0-20° | Leo |
| Moon | Taurus 3° | Scorpio 3° | Taurus 3-30° | Cancer |
| Mars | Capricorn 28° | Cancer 28° | Aries 0-12° | Aries, Scorpio |
| Mercury | Virgo 15° | Pisces 15° | Virgo 15-20° | Gemini, Virgo |
| Jupiter | Cancer 5° | Capricorn 5° | Sagittarius 0-10° | Sagittarius, Pisces |
| Venus | Pisces 27° | Virgo 27° | Libra 0-15° | Taurus, Libra |
| Saturn | Libra 20° | Aries 20° | Aquarius 0-20° | Capricorn, Aquarius |

### Retrograde
- **Definition**: Apparent backward motion from Earth's perspective
- **Calculation**: Swiss Ephemeris returns speed < 0
- **Rahu/Ketu**: Always retrograde (mean nodes)

### Combustion (Asta)
| Planet | Combustion Range (degrees from Sun) |
|--------|--------------------------------------|
| Moon | 12° |
| Mars | 17° |
| Mercury | 14° (12° if retrograde) |
| Jupiter | 11° |
| Venus | 10° (8° if retrograde) |
| Saturn | 15° |

### Aspects (Drishti)
- **All planets**: 7th house (180°) — full aspect
- **Mars**: 4th (90°) and 8th (210°) — full aspect
- **Jupiter**: 5th (150°) and 9th (270°) — full aspect
- **Saturn**: 3rd (60°) and 10th (300°) — full aspect
- **Rahu/Ketu**: 5th, 7th, 9th (same as Jupiter)

### Yogas (MVP: Core Set)
1. **Raja Yogas**: Kendra-Kona lord associations
2. **Dhana Yogas**: 2nd/11th lord associations
3. **Pancha Mahapurusha Yogas**: 5 planets in own/exalted signs in kendras
4. **Gaja Kesari**: Jupiter in kendra from Moon
5. **Chandra-Mangala**: Moon-Mars conjunction
6. **Kemadruma**: Moon isolated (no planets in 2nd/12th from Moon)

### Calculation Configuration Stored Per Chart
```json
{
  "ayanamsha": "lahiri",
  "house_system": "whole_sign",
  "planets": ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"],
  "divisional_charts": ["D1", "D9", "D10", "D12"],
  "dasha_system": "vimshottari",
  "dasha_levels": 3,
  "aspect_rules": "parashara",
  "combustion_rules": "standard",
  "retrograde_calculation": "mean_node",
  "precision_arcseconds": 0.01
}
```

### Input Requirements
- Date of birth (Gregorian)
- Exact birth time (HH:MM, 24-hour)
- Birthplace (city name + lat/lon)
- Timezone (IANA identifier, e.g., "America/New_York")
- Latitude/Longitude (decimal degrees, WGS84)

### Output Requirements
All longitudes in sidereal degrees (0-360), with:
- Sign (0-11, Aries=0)
- Degree within sign (0-30)
- Nakshatra (1-27)
- Pada (1-4)
- House (1-12, whole sign)
- Retrograde flag
- Combustion flag
- Dignity status