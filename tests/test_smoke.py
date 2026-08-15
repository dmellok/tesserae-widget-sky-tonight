"""Unit tests for sky_tonight.

Everything here is computed, so these run offline and are fully deterministic:
each one pins a real position at a real instant. The reference values come from
JPL Horizons and from geometry that cannot be argued with (the celestial pole
sits at the observer's latitude, due south from the southern hemisphere).
"""

from __future__ import annotations

import base64
import math
import struct
import zlib

import server

astro = server.astro
catalog = server.catalog

MERNDA = {"latitude": -37.635, "longitude": 145.095, "label": "Mernda"}
# 2026-08-15 21:00 AEST = 11:00 UT
D = astro.day_number(2026, 8, 15, 11.0)
LST = astro.lst(D, 11.0, 145.095)
LAT = -37.635


def _sep(ra1, dec1, ra2, dec2):
    """Angular separation in arcminutes."""
    a1, d1, a2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * 60


# ----- geometry -------------------------------------------------------


def test_celestial_pole_sits_at_the_observers_latitude():
    alt, az = astro.altaz(0.0, -90.0, LST, LAT)
    assert abs(alt - abs(LAT)) < 1e-6
    assert abs(az - 180.0) < 1e-6


def test_zenith_projects_to_the_centre_and_horizon_to_the_rim():
    assert server._project(90.0, 0.0) == (0.0, 0.0)
    x, y = server._project(0.0, 0.0)
    assert abs(math.hypot(x, y) - server.UNIT) < 1e-6
    assert server._project(-0.5, 0.0) is None


def test_east_is_drawn_on_the_left():
    """Looking up, not down: a star due east must land at negative x."""
    x, _y = server._project(45.0, 90.0)
    assert x < 0


# ----- frames ---------------------------------------------------------


def test_precession_shifts_a_star_by_tens_of_arcminutes_by_2026():
    """General precession is ~50"/yr, but how much of it lands on a given star
    depends on where the star sits, so this is a band rather than a value:
    Sirius moves 17', while bodies near the ecliptic in Leo move about 22'."""
    ra, dec = 101.287, -16.716                     # Sirius, J2000
    moved = _sep(ra, dec, *astro.precess(ra, dec, D))
    assert 12.0 < moved < 30.0


def test_precession_round_trips():
    ra, dec = 101.287, -16.716
    there = astro.precess(ra, dec, D, to_date=True)
    back = astro.precess(there[0], there[1], D, to_date=False)
    assert _sep(ra, dec, *back) < 0.01


# ----- ephemerides, against JPL Horizons ------------------------------


def test_sun_and_planets_match_horizons():
    """Reference RA/Dec pulled from JPL Horizons for 2026-08-15 12:00 UT,
    converted here from equinox-of-date back to the J2000 frame Horizons uses."""
    dd = astro.day_number(2026, 8, 15, 12.0)
    expect = {                       # J2000 astrometric, degrees
        "Sun": (144.679, 14.070),
        "Venus": (186.961, -4.564),
        "Mars": (92.584, 23.708),
        "Jupiter": (132.370, 18.277),
        "Saturn": (13.932, 3.151),
    }
    for name, (jra, jdec) in expect.items():
        if name == "Sun":
            ra, dec, *_ = astro.sun(dd)
        else:
            ra, dec, *_ = astro.planet(name, dd)
        ra, dec = astro.precess(ra, dec, dd, to_date=False)
        assert _sep(ra, dec, jra, jdec) < 3.0, f"{name} off by too much"


def test_moon_matches_horizons_and_reports_a_thin_waxing_crescent():
    dd = astro.day_number(2026, 8, 15, 12.0)
    ra, dec, _elong, _pa, illum, waxing = astro.moon(dd)
    ra, dec = astro.precess(ra, dec, dd, to_date=False)
    assert _sep(ra, dec, 177.447, -1.680) < 5.0
    assert 0.0 <= illum <= 0.15
    assert waxing is True


def test_sunrise_and_sunset_agree_with_open_meteo():
    """Open-Meteo published 07:05 / 17:43 local for Mernda on 2026-08-14."""
    def alt_at(ut):
        d = astro.day_number(2026, 8, 14, ut)
        ra, dec, *_ = astro.sun(d)
        return astro.altaz(ra, dec, astro.lst(d, ut, 145.095), LAT)[0]

    def crossing(lo, hi):
        for _ in range(60):
            mid = (lo + hi) / 2
            if (alt_at(lo) + 0.833) * (alt_at(mid) + 0.833) <= 0:
                hi = mid
            else:
                lo = mid
        return ((lo + hi) / 2 + 10.0) % 24        # -> AEST

    assert abs(crossing(18.0, 23.0) - (7 + 5 / 60)) < 2 / 60
    assert abs(crossing(4.0, 9.0) - (17 + 43 / 60)) < 2 / 60


# ----- catalogue ------------------------------------------------------


def test_brightest_catalogue_entry_is_sirius():
    raw = zlib.decompress(base64.b64decode(catalog.STARS_B64))
    ra, dec, mag = struct.unpack_from("<HhB", raw, 0)
    assert _sep(ra / 65535 * 360, dec / 180, 101.287, -16.716) < 2.0
    assert abs((mag / 25.0 - 2.0) + 1.44) < 0.05


def test_constellation_label_coordinates_are_degrees_not_hours():
    """Regression: the source gives degrees on -180..180. Reading them as hours
    and multiplying by 15 put Orion overhead on an August evening in Melbourne."""
    for abbr, (_name, ra, dec) in catalog.CONSTELLATIONS.items():
        assert 0.0 <= ra < 360.0, f"{abbr} RA out of range"
        assert -90.0 <= dec <= 90.0, f"{abbr} Dec out of range"
    _n, ra, dec = catalog.CONSTELLATIONS["Ori"]
    alt, _az = astro.altaz(*astro.precess(ra, dec, D), LST, LAT)
    assert alt < -20, "Orion must be well below a Melbourne August evening horizon"
    _n, ra, dec = catalog.CONSTELLATIONS["Sco"]
    alt, _az = astro.altaz(*astro.precess(ra, dec, D), LST, LAT)
    assert alt > 55, "Scorpius should be near the zenith"


# ----- payload --------------------------------------------------------


def test_fetch_without_a_location_asks_for_one():
    out = server.fetch({}, {}, ctx={})
    assert "error" in out and "location" in out["error"].lower()


def test_fetch_returns_a_drawable_chart():
    out = server.fetch({**MERNDA, "when": "21", "mag": "5.0"}, {}, ctx={})
    assert out.get("error") is None
    assert out["star_count"] > 300
    assert out["lines"].startswith("M")
    assert out["twilight"] == "Night"
    assert all(math.hypot(s[0], s[1]) <= server.UNIT + 1 for s in out["stars"])


def test_no_two_labels_overlap_once_drawn():
    """Checked as boxes, not distances. A label past FLIP_AT opens leftward, so
    two markers a comfortable distance apart can still collide text-to-text —
    which is exactly how Venus landed on top of Spica."""
    for when in ("20", "21", "22"):
        out = server.fetch({**MERNDA, "when": when, "mag": "5.0"}, {}, ctx={})
        boxes = [server._label_box(p["x"], p["y"], p["n"], "planet")
                 for p in out["planets"] if p.get("lbl")]
        boxes += [server._label_box(s["x"], s["y"], s["t"], "star") for s in out["starnames"]]
        boxes += [server._label_box(a["x"], a["y"], a["t"], "const") for a in out["labels"]]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert not server._overlaps(a, b), f"labels collide at {when}:00"


def test_a_fixed_hour_in_the_morning_means_the_coming_evening():
    from datetime import datetime
    morning = datetime(2026, 8, 15, 9, 30).astimezone()
    assert server._when("21", morning).day == 15
    small_hours = datetime(2026, 8, 15, 2, 0).astimezone()
    assert server._when("21", small_hours).day == 14
