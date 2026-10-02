"""
Golden Test Charts — Verified Vedic Charts for Validation

IMPORTANT — READ BEFORE TRUSTING THIS FILE
==========================================

`expected` values below are **ENGINE OUTPUT SNAPSHOTS**, not independent
reference data. They were produced by running this engine and recording what
it returned. They therefore prove only that the engine is *deterministic and
regression-stable* — they do NOT prove the engine is *correct*.

They are labelled `verified_against` accordingly:
  "self-snapshot"  -> regression guard only, NOT a correctness claim
  "external-source" -> independently sourced and cross-checked

To claim Gate 1 ("100% agreement on sign assignment") you must replace every
self-snapshot entry with data from an independent source (Astro-Databank,
Jagannatha Hora, or a published book) and set verified_against accordingly.
`test_no_self_snapshots_remain` enforces that this is not forgotten.

Sources to use for genuine verification:
  - Astro-Databank (https://www.astro.com/astro-databank)  [AA-rated only]
  - Jagannatha Hora (free, cross-platform, independently implemented)
  - Swiss Ephemeris official test data
"""

GOLDEN_CHARTS = [
    {
        "name": "Lord Rama (Traditional)",
        "source": "Traditional / Valmiki Ramayana",
        "verified_against": "self-snapshot",
        "birth_data": {
            # BCE date. Outside both the Swiss Ephemeris file range and the
            # Moshier range, so this chart is NOT calculable by this engine yet.
            "datetime": "5114-01-10T12:00:00",
            "timezone": "Asia/Kolkata",
            "latitude": 26.7889,    # Ayodhya
            "longitude": 82.1978,
        },
        "expected": {
            "lagna_sign": 5,
            "sun_sign": 9,
        },
        "notes": "Out of ephemeris range. Excluded from active assertions.",
        "skip": True,
    },
    {
        "name": "Adi Shankaracharya",
        "source": "Traditional (traditional/legendary chronology)",
        "verified_against": "unusable",
        "skip": True,
        "birth_data": {
            "datetime": "788-05-11T12:00:00",
            "timezone": "Asia/Kolkata",
            "latitude": 10.7905,    # Kalady, Kerala
            "longitude": 76.4476,
        },
        "expected": {},
        "notes": (
            "EXCLUDED. The date derives from traditional chronology with no "
            "documentary basis, and the birth time (here 12:00) is entirely "
            "assumed. Traditional sources also place him in several mutually "
            "inconsistent locations. Nothing about this chart is verifiable."
        ),
    },
    {
        "name": "Albert Einstein",
        "source": (
            "Astro-Databank (Rodden AA, birth certificate in hand, "
            "Stadtarchiv Ulm) + cross-checked against VedAstro, an "
            "independent implementation"
        ),
        "verified_against": "external-source",
        "birth_data": {
            "datetime": "1879-03-14T11:30:00",
            # Astro-Databank records the timezone as "LMT m10e0" = +0:40.
            # IANA's Europe/Berlin LMT for 1879 is +0:53:28, because tzdb
            # uses the zone's historical reference meridian rather than the
            # stated longitude. The 13.5-minute difference is documented
            # rather than silently resolved; see test_lmt_ambiguity_is_material.
            "timezone": "Europe/Berlin",
            "latitude": 48.3988,    # Ulm, Germany
            "longitude": 9.9916,
        },
        "expected": {
            "lagna_sign": 2,        # Gemini
            "sun_sign": 11,         # Pisces
            "moon_sign": 7,         # Scorpio
            "moon_nakshatra": 18,   # Jyeshtha
        },
        "verified_quantities": [
            "lagna_sign", "sun_sign", "moon_sign", "moon_nakshatra",
        ],
        "notes": (
            "Rodden AA: birth certificate states 11:30. VedAstro, an "
            "independent implementation, independently reports lagna Gemini, "
            "Sun Pisces, Moon Scorpio in Jyeshtha. All four match."
        ),
    },
    {
        "name": "Mahatma Gandhi",
        "source": "Astro-Databank — Rodden rating NOT AA",
        "verified_against": "unusable",
        "skip": True,
        "birth_data": {
            "datetime": "1869-10-02T07:45:00",
            "timezone": "Asia/Kolkata",
            "latitude": 21.6417,    # Porbandar
            "longitude": 69.6093,
        },
        "expected": {},
        "notes": (
            "EXCLUDED. Astro-Databank lists this as 'Rectified from approx. "
            "time' with no birth certificate, and conflicting times appear "
            "across sources: 07:08:12 LMT (Fagan, astro.com), 07:45 LMT "
            "(Huggins, and the time this engine previously used), 07:33, "
            "07:56 IST, and 02:29:48 GMT. A 37-minute spread is roughly 9 "
            "degrees of ascendant, which can change the whole-sign house. "
            "Including this chart as a 'golden' case would have meant "
            "testing the engine against a guess. Kept in the file as a "
            "documented exclusion rather than deleted."
        ),
    },
    {
        "name": "Sri Ramana Maharshi",
        "source": (
            "Astro-Databank (Rodden B, from Natarajan's biography "
            "'Timeless in Time') + cross-checked against the traditional "
            "biographical account, which independently names the Moon's "
            "nakshatra"
        ),
        "verified_against": "external-source-partial",
        "birth_data": {
            "datetime": "1879-12-30T01:00:00",
            "timezone": "Asia/Kolkata",
            "latitude": 9.5167,     # Aruppukkottai, 9n31
            "longitude": 78.1,      # 78e06
            "city": "Aruppukkottai",
        },
        "expected": {
            # The biography records: "The procession of Bhuminatheswara was
            # slowly returning to the temple at 1 a.m. The star in the
            # constellation was Punarvasu." That is an independent,
            # non-astrology author's statement about the Moon's sidereal
            # nakshatra, and the engine reproduces it.
            "moon_nakshatra": 7,    # Punarvasu
            "moon_nakshatra_name": "Punarvasu",
        },
        "verified_quantities": ["moon_nakshatra"],
        "notes": (
            "PARTIAL. The Moon's nakshatra matches an independent traditional "
            "source, confirming sidereal position to within 13.33 degrees. "
            "The ascendant, Sun and other planets are NOT externally verified "
            "for this chart. Birth time is biographical (Rodden B, not a "
            "certificate); David Frawley gives 01:15 with no source."
        ),
    },
    {
        "name": "J. Krishnamurti",
        "source": "Astro-Databank / Wikipedia — Rodden rating B",
        "verified_against": "unusable",
        "skip": True,
        "birth_data": {
            "datetime": "1895-05-11T00:30:00",
            "timezone": "Asia/Kolkata",
            "latitude": 13.6288,    # Madanapalle
            "longitude": 78.5047,
        },
        "expected": {},
        "notes": (
            "EXCLUDED. Wikipedia states the birth date 'is a matter of "
            "dispute', citing claims spanning 4 May 1895 to 25 May 1896. "
            "Astro-Seek lists the time as 00:30 LST with a Rodden rating of "
            "B (Borges). The engine previously used 08:30, which no source "
            "supports; a date that is not agreed upon cannot anchor a test."
        ),
    },
    {
        "name": "Epoch control case",
        "source": "Synthetic, analytically derivable",
        "verified_against": "external-source",
        "birth_data": {
            "datetime": "1990-01-01T12:00:00",
            "timezone": "UTC",
            "latitude": 0.0,        # Equator
            "longitude": 0.0,       # Prime Meridian
        },
        "expected": {
            # Independently checkable from an ephemeris, not from this engine:
            # Sun's tropical longitude on 1990-01-01 12:00 UT is 280.814 deg.
            # Lahiri ayanamsha is 23.717 deg, giving 257.097 deg sidereal,
            # which falls in Sagittarius (240-270) = sign index 8 (Aries=0).
            "sun_sign": 8,
        },
        "notes": "Sole chart with an independently derivable expectation.",
    },
]


# Expected nakshatra boundaries (sidereal degrees)
# Each nakshatra = 13°20' = 13.333...°
NAKSHATRA_BOUNDARIES = [
    (0, 13.333333),       # Ashwini
    (13.333333, 26.666667), # Bharani
    (26.666667, 40.0),    # Krittika
    (40.0, 53.333333),    # Rohini
    (53.333333, 66.666667), # Mrigashira
    (66.666667, 80.0),    # Ardra
    (80.0, 93.333333),    # Punarvasu
    (93.333333, 106.666667), # Pushya
    (106.666667, 120.0),  # Ashlesha
    (120.0, 133.333333),  # Magha
    (133.333333, 146.666667), # Purva Phalguni
    (146.666667, 160.0),  # Uttara Phalguni
    (160.0, 173.333333),  # Hasta
    (173.333333, 186.666667), # Chitra
    (186.666667, 200.0),  # Swati
    (200.0, 213.333333),  # Vishakha
    (213.333333, 226.666667), # Anuradha
    (226.666667, 240.0),  # Jyeshtha
    (240.0, 253.333333),  # Mula
    (253.333333, 266.666667), # Purva Ashadha
    (266.666667, 280.0),  # Uttara Ashadha
    (280.0, 293.333333),  # Shravana
    (293.333333, 306.666667), # Dhanishta
    (306.666667, 320.0),  # Shatabhisha
    (320.0, 333.333333),  # Purva Bhadrapada
    (333.333333, 346.666667), # Uttara Bhadrapada
    (346.666667, 360.0),  # Revati
]


# Vimshottari dasha periods for verification
DASHA_VERIFICATION = {
    # Moon in Ashwini (0-13.33°) -> Ketu dasha first
    "moon_in_ashwini": {
        "first_lord": "ketu",
        "first_remaining_max": 7,  # years
    },
    # Moon in Bharani (13.33-26.67°) -> Venus dasha first
    "moon_in_bharani": {
        "first_lord": "venus",
        "first_remaining_max": 20,
    },
    # Moon in Krittika (26.67-40°) -> Sun dasha first
    "moon_in_krittika": {
        "first_lord": "sun",
        "first_remaining_max": 6,
    },
}


# Divisional chart verification
# D9 (Navamsa): Each sign divided into 9 parts of 3°20'
# Planet at 0° Aries -> D9 Aries
# Planet at 3°20' Aries -> D9 Taurus
# Planet at 10° Aries -> D9 Cancer (3 parts = 9 signs forward = Cancer)

DIVISIONAL_VERIFICATION = {
    "d9_sun_at_0_aries": {"sign": 0},      # Aries
    "d9_sun_at_3_20_aries": {"sign": 1},   # Taurus
    "d9_sun_at_10_aries": {"sign": 3},     # Cancer
    "d9_sun_at_30_aries": {"sign": 0},     # Taurus (next sign)
}


# Tolerance settings for tests
TOLERANCES = {
    "longitude_degrees": 0.1,      # ±0.1°
    "sign_match": True,            # Must match exactly
    "nakshatra_match": True,       # Must match exactly
    "dasha_date_days": 7,          # ±7 days
    "house_match": True,           # Must match exactly (whole sign)
}