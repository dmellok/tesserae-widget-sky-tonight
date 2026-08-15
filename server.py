"""sky_tonight — the sky over your location, right now, computed not fetched.

Runs on the Tesserae side, never the client. Returns a JSON-serialisable dict,
or {"error": "friendly message"}; never raises.

There is no API and no network call. The star catalogue is baked into
catalog.py and every position is computed here: hour angles from the Sun's mean
longitude, planets and the Moon from Schlyter's elements, all validated against
JPL Horizons to under two arcminutes.

One frame subtlety runs through the whole file. The catalogue is J2000, but an
hour angle is measured from the equinox OF DATE, so the stars are precessed
forward before projection. Skip it and by 2026 every star is ~22 arcmin out —
a smear the whole chart shares equally, which reads as a projection bug rather
than a frame bug.

Projection is stereographic from the zenith: r = tan(z/2), normalised so the
horizon lands at r = 1. North is up and East is LEFT, because you are looking
up at the sky rather than down at a map.
"""

from __future__ import annotations

import base64
import importlib.util
import math
import os
import struct
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))


def _sibling(name: str):
    """Import a module sitting next to this file, whatever sys.path looks like."""
    spec = importlib.util.spec_from_file_location(
        f"sky_tonight_{name}", os.path.join(_HERE, f"{name}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


astro = _sibling("astro")
catalog = _sibling("catalog")

RAD = math.pi / 180.0
UNIT = 1000.0                      # horizon radius in the client's viewBox units

PLANET_ORDER = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]
PLANET_SYMBOL = {
    "Mercury": "☿", "Venus": "♀", "Mars": "♂", "Jupiter": "♃",
    "Saturn": "♄", "Uranus": "♅", "Neptune": "♆",
}
# rough mean apparent magnitudes; only used to size the dot
PLANET_MAG = {
    "Mercury": -0.2, "Venus": -4.1, "Mars": 0.7, "Jupiter": -2.2,
    "Saturn": 0.6, "Uranus": 5.7, "Neptune": 7.8,
}

MOON_PHASES = [
    (0.02, "New moon"), (0.24, "Waxing crescent"), (0.27, "First quarter"),
    (0.49, "Waxing gibbous"), (0.52, "Full moon"), (0.74, "Waning gibbous"),
    (0.77, "Last quarter"), (0.99, "Waning crescent"), (1.01, "New moon"),
]


def _stars():
    """Decode the packed catalogue into (ra, dec, mag), brightest first."""
    raw = zlib.decompress(base64.b64decode(catalog.STARS_B64))
    out = []
    for i in range(0, len(raw), 5):
        ra, dec, mag = struct.unpack_from("<HhB", raw, i)
        out.append((ra / 65535.0 * 360.0, dec / 180.0, mag / 25.0 - 2.0))
    return out


_STAR_CACHE: list | None = None


def _star_list():
    global _STAR_CACHE
    if _STAR_CACHE is None:
        _STAR_CACHE = _stars()
    return _STAR_CACHE


def _project(alt: float, az: float):
    """Alt/az -> chart x,y. Returns None below the horizon."""
    if alt < 0:
        return None
    z = (90.0 - alt) * RAD
    r = math.tan(z / 2.0) * UNIT
    return (-r * math.sin(az * RAD), -r * math.cos(az * RAD))


def _phase_name(illum: float, waxing: bool) -> str:
    x = illum / 2.0 if waxing else 1.0 - illum / 2.0
    for edge, name in MOON_PHASES:
        if x <= edge:
            return name
    return "New moon"


# Approximate label metrics in chart units. They only need to be close: the
# point is to reserve the right SHAPE of space, and a label is a wide flat box,
# not a circle.
LABEL_H = 52.0
CHAR_W = {"star": 23.0, "planet": 26.0, "const": 25.0}
FLIP_AT = UNIT * 0.55          # must match sideText() in client.js
GAP = {"star": 28.0, "planet": 34.0}


def _label_box(x: float, y: float, text: str, kind: str) -> list[float]:
    """The rectangle a label will actually occupy once drawn.

    Comparing marker positions is not enough: past FLIP_AT a label opens to the
    LEFT so it stays on the disc, which means a flipped label and an unflipped
    one 190 units apart still run into each other head-on. Venus over Spica was
    exactly that.
    """
    w = CHAR_W[kind] * len(text)
    if kind == "const":
        x0 = x - w / 2.0                                   # centred on the point
    else:
        x0 = x - GAP[kind] - w if x > FLIP_AT else x + GAP[kind]
    return [x0, y - LABEL_H / 2, x0 + w, y + LABEL_H / 2]


def _overlaps(a: list[float], b: list[float], pad: float = 10.0) -> bool:
    return not (a[2] + pad < b[0] or b[2] + pad < a[0]
                or a[3] + pad < b[1] or b[3] + pad < a[1])


def _place(items: list, kind: str, taken: list) -> list:
    """Keep labels in priority order, reserving each one's box as it lands."""
    out = []
    for it in items:
        box = _label_box(it["x"], it["y"], it["t"], kind)
        if any(_overlaps(box, b) for b in taken):
            continue
        taken.append(box)
        out.append(it)
    return out


def _twilight(sun_alt: float) -> str:
    if sun_alt > 0:
        return "Daylight"
    if sun_alt > -6:
        return "Civil twilight"
    if sun_alt > -12:
        return "Nautical twilight"
    if sun_alt > -18:
        return "Astronomical twilight"
    return "Night"


def _when(option: str, now_local: datetime) -> datetime:
    """Resolve the 'when' option to a local datetime."""
    if option in ("now", "", None):
        return now_local
    try:
        hour = int(option)
    except (TypeError, ValueError):
        return now_local
    target = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    # "9pm tonight" means the coming evening for most of the day, but between
    # midnight and dawn you are still inside the previous evening's sky, so it
    # means the one that has just been rather than the one 21 hours away.
    if now_local.hour < 6 and hour >= 12:
        target -= timedelta(days=1)
    return target


def _lines_paths(lst_deg: float, lat: float, d: float) -> str:
    """Constellation figures, precessed, horizon-clipped, as one SVG path.

    Segments are subdivided before projection for two reasons: it clips cleanly
    at the horizon, and a stereographic projection maps a great circle to an
    arc, so a long segment drawn straight would visibly bow away from the stars
    it is meant to join.
    """
    out = []
    for poly in catalog.CONST_LINES:
        run: list[str] = []
        prev = None
        for ra0, dec0 in poly:
            pts = []
            if prev is not None:
                span = math.hypot(((ra0 - prev[0] + 180) % 360) - 180, dec0 - prev[1])
                steps = max(1, int(span / 3.0))
                for s in range(1, steps):
                    f = s / steps
                    dra = ((ra0 - prev[0] + 180) % 360) - 180
                    pts.append((prev[0] + dra * f, prev[1] + (dec0 - prev[1]) * f))
            pts.append((ra0, dec0))
            for ra, dec in pts:
                pra, pdec = astro.precess(ra, dec, d)
                alt, az = astro.altaz(pra, pdec, lst_deg, lat)
                xy = _project(alt, az)
                if xy is None:
                    if len(run) > 1:
                        out.append("M" + "L".join(run))
                    run = []
                else:
                    run.append(f"{xy[0]:.1f} {xy[1]:.1f}")
            prev = (ra0, dec0)
        if len(run) > 1:
            out.append("M" + "L".join(run))
    return "".join(out)


def fetch(
    options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]
) -> dict[str, Any]:
    try:
        lat = float(options.get("latitude"))
        lon = float(options.get("longitude"))
    except (TypeError, ValueError):
        return {"error": "Set a location in this cell's settings to draw its sky."}

    label = str(options.get("label") or options.get("location") or "").strip()
    try:
        maglim = float(options.get("mag") or 5.0)
    except (TypeError, ValueError):
        maglim = 5.0

    now_local = datetime.now().astimezone()
    when_local = _when(str(options.get("when") or "now"), now_local)
    when_utc = when_local.astimezone(timezone.utc)
    ut_hours = when_utc.hour + when_utc.minute / 60.0 + when_utc.second / 3600.0
    d = astro.day_number(when_utc.year, when_utc.month, when_utc.day, ut_hours)
    lst_deg = astro.lst(d, ut_hours, lon)

    # ---- stars ----
    stars = []
    for ra, dec, mag in _star_list():
        if mag > maglim:
            break                                  # catalogue is sorted brightest first
        pra, pdec = astro.precess(ra, dec, d)
        alt, az = astro.altaz(pra, pdec, lst_deg, lat)
        xy = _project(alt, az)
        if xy is not None:
            stars.append([round(xy[0], 1), round(xy[1], 1), round(mag, 1)])

    # ---- named stars ----
    starnames = []
    for ra, dec, name, mag in catalog.STAR_NAMES:
        pra, pdec = astro.precess(ra, dec, d)
        alt, az = astro.altaz(pra, pdec, lst_deg, lat)
        xy = _project(alt, az)
        if xy is not None and alt > 8:             # skip the murk right at the rim
            starnames.append({"t": name, "x": round(xy[0], 1), "y": round(xy[1], 1),
                              "m": round(mag, 2)})
    starnames.sort(key=lambda s: s["m"])

    # ---- constellation labels ----
    labels = []
    for abbr, (name, ra, dec) in catalog.CONSTELLATIONS.items():
        pra, pdec = astro.precess(ra, dec, d)
        alt, az = astro.altaz(pra, pdec, lst_deg, lat)
        xy = _project(alt, az)
        if xy is not None and alt > 12:
            labels.append({"t": name, "a": abbr, "x": round(xy[0], 1),
                           "y": round(xy[1], 1), "alt": round(alt, 1)})
    labels.sort(key=lambda s: -s["alt"])

    # ---- sun, moon, planets ----
    sra, sdec, *_ = astro.sun(d)
    sun_alt, sun_az = astro.altaz(sra, sdec, lst_deg, lat)
    sun_xy = _project(sun_alt, sun_az)

    mra, mdec, elong, _pa, illum, waxing = astro.moon(d)
    moon_alt, moon_az = astro.altaz(mra, mdec, lst_deg, lat)
    moon_xy = _project(moon_alt, moon_az)
    moon = {
        "illum": round(illum, 3),
        "waxing": bool(waxing),
        "phase": _phase_name(illum, waxing),
        "alt": round(moon_alt, 1),
        "up": moon_xy is not None,
        # From the southern hemisphere a waxing Moon is lit on the LEFT, not the
        # right: the whole sky is effectively turned over. Drawing the northern
        # convention here would be visibly wrong out the window.
        "flip": lat < 0,
    }
    if moon_xy:
        moon["x"], moon["y"] = round(moon_xy[0], 1), round(moon_xy[1], 1)

    planets = []
    for name in PLANET_ORDER:
        pra, pdec, *_ = astro.planet(name, d)
        alt, az = astro.altaz(pra, pdec, lst_deg, lat)
        xy = _project(alt, az)
        if xy is None:
            continue
        planets.append({
            "n": name, "s": PLANET_SYMBOL[name], "m": PLANET_MAG[name],
            "x": round(xy[0], 1), "y": round(xy[1], 1), "alt": round(alt, 1),
        })
    # Only ship what the chart will actually draw, or the payload reserves
    # label space for bodies nobody can see. Neptune at mag 7.8 was blocking
    # Saturn's name.
    planets = [p for p in planets if p["m"] < 6.0]
    planets.sort(key=lambda p: p["m"])

    # A planet always keeps its dot; only the NAME yields when two crowd each
    # other, brightest winning.
    taken: list = []
    for p in planets:
        box = _label_box(p["x"], p["y"], p["n"], "planet")
        p["lbl"] = not any(_overlaps(box, b) for b in taken)
        if p["lbl"]:
            taken.append(box)

    # Priority runs planets > star names > constellation names, and each layer
    # dodges the ones above it. Planets go first because a labelled planet is
    # the thing most worth reading on any given night.
    starnames = _place(starnames, "star", taken)[:12]
    labels = _place(labels, "const", taken)[:14]

    naked_eye = [p for p in planets if p["m"] < 4.0]

    return {
        "label": label or f"{abs(lat):.1f}°{'S' if lat < 0 else 'N'}",
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "when": when_local.strftime("%Y-%m-%dT%H:%M"),
        "time": when_local.strftime("%H:%M"),
        "date": when_local.strftime("%a %d %b"),
        "is_now": str(options.get("when") or "now") == "now",
        "stars": stars,
        "star_count": len(stars),
        "lines": _lines_paths(lst_deg, lat, d) if options.get("show_lines", True) is not False else "",
        "labels": labels,
        "starnames": starnames,
        "planets": planets,
        "planets_up": len(naked_eye),
        "planet_list": ", ".join(p["n"] for p in naked_eye) or "none up",
        "moon": moon,
        "moon_phase": moon["phase"],
        "moon_illum": round(illum * 100),
        "sun": {"alt": round(sun_alt, 1),
                **({"x": round(sun_xy[0], 1), "y": round(sun_xy[1], 1)} if sun_xy else {})},
        "sun_alt": round(sun_alt, 1),
        "twilight": _twilight(sun_alt),
        "dark": sun_alt < -18,
        "theme": str(options.get("theme") or "chart"),
        "layout": str(options.get("layout") or "board"),
        "mag": maglim,
        "show_lines": options.get("show_lines", True) is not False,
        "show_labels": options.get("show_labels", True) is not False,
        "show_star_names": options.get("show_star_names", True) is not False,
        "show_planets": options.get("show_planets", True) is not False,
    }
