"""Low-precision ephemerides, stdlib only.

Paul Schlyter's method (stjarnhimlen.se/comp/ppcomp.html): good to roughly an
arcminute for the Sun and planets and a couple for the Moon, which is far
finer than a star chart drawn a few hundred pixels across can show.
"""
from __future__ import annotations

import math

RAD = math.pi / 180.0
DEG = 180.0 / math.pi


def _norm(x: float) -> float:
    return x % 360.0


def day_number(y: int, mo: int, d: int, ut_hours: float) -> float:
    """Days since 2000 Jan 0.0 TDT."""
    dd = 367 * y - 7 * (y + (mo + 9) // 12) // 4 + 275 * mo // 9 + d - 730530
    return dd + ut_hours / 24.0


def _ecl_to_eq(xe: float, ye: float, ze: float, obl: float):
    return (
        xe,
        ye * math.cos(obl * RAD) - ze * math.sin(obl * RAD),
        ye * math.sin(obl * RAD) + ze * math.cos(obl * RAD),
    )


def _to_radec(x: float, y: float, z: float):
    ra = _norm(math.atan2(y, x) * DEG)
    dec = math.atan2(z, math.hypot(x, y)) * DEG
    return ra, dec


def sun(d: float):
    """(ra, dec, ecliptic_longitude, mean_anomaly, perihelion) in degrees."""
    w = 282.9404 + 4.70935e-5 * d
    e = 0.016709 - 1.151e-9 * d
    M = _norm(356.0470 + 0.9856002585 * d)
    obl = 23.4393 - 3.563e-7 * d
    E = M + DEG * e * math.sin(M * RAD) * (1 + e * math.cos(M * RAD))
    xv = math.cos(E * RAD) - e
    yv = math.sqrt(1 - e * e) * math.sin(E * RAD)
    v = math.atan2(yv, xv) * DEG
    r = math.hypot(xv, yv)
    lon = _norm(v + w)
    xs, ys = r * math.cos(lon * RAD), r * math.sin(lon * RAD)
    ra, dec = _to_radec(*_ecl_to_eq(xs, ys, 0.0, obl))
    return ra, dec, lon, M, w


def gmst0(d: float) -> float:
    _, _, _, M, w = sun(d)
    return _norm(M + w + 180.0)


def lst(d: float, ut_hours: float, lon_east: float) -> float:
    """Local sidereal time in degrees."""
    return _norm(gmst0(d) + ut_hours * 15.0 + lon_east)


def altaz(ra: float, dec: float, lst_deg: float, lat: float):
    """Equatorial -> (altitude, azimuth). Azimuth is from North, through East."""
    H = (lst_deg - ra) * RAD
    dr, lr = dec * RAD, lat * RAD
    sin_alt = math.sin(dr) * math.sin(lr) + math.cos(dr) * math.cos(lr) * math.cos(H)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt) * DEG
    az = math.atan2(
        -math.cos(dr) * math.sin(H),
        math.sin(dr) * math.cos(lr) - math.cos(dr) * math.sin(lr) * math.cos(H),
    ) * DEG
    return alt, _norm(az)


def moon(d: float):
    """(ra, dec, elongation, phase_angle, illuminated_fraction)."""
    N = _norm(125.1228 - 0.0529538083 * d)
    i = 5.1454
    w = _norm(318.0634 + 0.1643573223 * d)
    a = 60.2666
    e = 0.054900
    M = _norm(115.3654 + 13.0649929509 * d)

    E = M + DEG * e * math.sin(M * RAD) * (1 + e * math.cos(M * RAD))
    for _ in range(3):
        E = E - (E - DEG * e * math.sin(E * RAD) - M) / (1 - e * math.cos(E * RAD))
    xv = a * (math.cos(E * RAD) - e)
    yv = a * math.sqrt(1 - e * e) * math.sin(E * RAD)
    v = _norm(math.atan2(yv, xv) * DEG)
    r = math.hypot(xv, yv)

    xh = r * (math.cos(N * RAD) * math.cos((v + w) * RAD)
              - math.sin(N * RAD) * math.sin((v + w) * RAD) * math.cos(i * RAD))
    yh = r * (math.sin(N * RAD) * math.cos((v + w) * RAD)
              + math.cos(N * RAD) * math.sin((v + w) * RAD) * math.cos(i * RAD))
    zh = r * math.sin((v + w) * RAD) * math.sin(i * RAD)

    lon = _norm(math.atan2(yh, xh) * DEG)
    lat_e = math.atan2(zh, math.hypot(xh, yh)) * DEG

    # the dozen largest perturbations; without these the Moon is out by ~1 degree
    _, _, Ls, Ms, _ = sun(d)
    Lm = _norm(N + w + M)
    D = _norm(Lm - Ls)
    F = _norm(Lm - N)
    lon += (-1.274 * math.sin((M - 2 * D) * RAD)
            + 0.658 * math.sin(2 * D * RAD)
            - 0.186 * math.sin(Ms * RAD)
            - 0.059 * math.sin((2 * M - 2 * D) * RAD)
            - 0.057 * math.sin((M - 2 * D + Ms) * RAD)
            + 0.053 * math.sin((M + 2 * D) * RAD)
            + 0.046 * math.sin((2 * D - Ms) * RAD)
            + 0.041 * math.sin((M - Ms) * RAD)
            - 0.035 * math.sin(D * RAD)
            - 0.031 * math.sin((M + Ms) * RAD)
            - 0.015 * math.sin((2 * F - 2 * D) * RAD)
            + 0.011 * math.sin((M - 4 * D) * RAD))
    lat_e += (-0.173 * math.sin((F - 2 * D) * RAD)
              - 0.055 * math.sin((M - F - 2 * D) * RAD)
              - 0.046 * math.sin((M + F - 2 * D) * RAD)
              + 0.033 * math.sin((F + 2 * D) * RAD)
              + 0.017 * math.sin((2 * M + F) * RAD))
    r += -0.58 * math.cos((M - 2 * D) * RAD) - 0.46 * math.cos(2 * D * RAD)

    obl = 23.4393 - 3.563e-7 * d
    cl, sl = math.cos(lat_e * RAD), math.sin(lat_e * RAD)
    xg = r * cl * math.cos(lon * RAD)
    yg = r * cl * math.sin(lon * RAD)
    zg = r * sl
    ra, dec = _to_radec(*_ecl_to_eq(xg, yg, zg, obl))

    elong = math.acos(max(-1.0, min(1.0, math.cos((Ls - lon) * RAD) * math.cos(lat_e * RAD)))) * DEG
    phase_angle = 180.0 - elong
    illum = (1 + math.cos(phase_angle * RAD)) / 2.0
    # signed so the client knows which limb is lit: waxing 0..1, waning -1..0
    waxing = math.sin((lon - Ls) * RAD) >= 0
    return ra, dec, elong, phase_angle, illum, waxing


PLANETS = {
    #        N              i        w              a         e            M
    "Mercury": ((48.3313, 3.24587e-5), (7.0047, 5.00e-8), (29.1241, 1.01444e-5),
                (0.387098, 0.0), (0.205635, 5.59e-10), (168.6562, 4.0923344368)),
    "Venus":   ((76.6799, 2.46590e-5), (3.3946, 2.75e-8), (54.8910, 1.38374e-5),
                (0.723330, 0.0), (0.006773, -1.302e-9), (48.0052, 1.6021302244)),
    "Mars":    ((49.5574, 2.11081e-5), (1.8497, -1.78e-8), (286.5016, 2.92961e-5),
                (1.523688, 0.0), (0.093405, 2.516e-9), (18.6021, 0.5240207766)),
    "Jupiter": ((100.4542, 2.76854e-5), (1.3030, -1.557e-7), (273.8777, 1.64505e-5),
                (5.20256, 0.0), (0.048498, 4.469e-9), (19.8950, 0.0830853001)),
    "Saturn":  ((113.6634, 2.38980e-5), (2.4886, -1.081e-7), (339.3939, 2.97661e-5),
                (9.55475, 0.0), (0.055546, -9.499e-9), (316.9670, 0.0334442282)),
    "Uranus":  ((74.0005, 1.3978e-5), (0.7733, 1.9e-8), (96.6612, 3.0565e-5),
                (19.18171, -1.55e-8), (0.047318, 7.45e-9), (142.5905, 0.011725806)),
    "Neptune": ((131.7806, 3.0173e-5), (1.7700, -2.55e-7), (272.8461, -6.027e-6),
                (30.05826, 3.313e-8), (0.008606, 2.15e-9), (260.2471, 0.005995147)),
}


def _helio(name: str, d: float):
    N0, i0, w0, a0, e0, M0 = PLANETS[name]
    N = _norm(N0[0] + N0[1] * d)
    i = i0[0] + i0[1] * d
    w = _norm(w0[0] + w0[1] * d)
    a = a0[0] + a0[1] * d
    e = e0[0] + e0[1] * d
    M = _norm(M0[0] + M0[1] * d)
    E = M + DEG * e * math.sin(M * RAD) * (1 + e * math.cos(M * RAD))
    for _ in range(5):
        E = E - (E - DEG * e * math.sin(E * RAD) - M) / (1 - e * math.cos(E * RAD))
    xv = a * (math.cos(E * RAD) - e)
    yv = a * math.sqrt(1 - e * e) * math.sin(E * RAD)
    v = _norm(math.atan2(yv, xv) * DEG)
    r = math.hypot(xv, yv)
    u = (v + w) * RAD
    xh = r * (math.cos(N * RAD) * math.cos(u) - math.sin(N * RAD) * math.sin(u) * math.cos(i * RAD))
    yh = r * (math.sin(N * RAD) * math.cos(u) + math.cos(N * RAD) * math.sin(u) * math.cos(i * RAD))
    zh = r * math.sin(u) * math.sin(i * RAD)
    return xh, yh, zh, M, r


def planet(name: str, d: float):
    xh, yh, zh, M, r = _helio(name, d)
    if name in ("Jupiter", "Saturn", "Uranus"):
        xh, yh, zh = _giant_perturb(name, d, xh, yh, zh)
    _, _, lon_s, Ms, ws = sun(d)
    Es = Ms + DEG * 0.016709 * math.sin(Ms * RAD) * (1 + 0.016709 * math.cos(Ms * RAD))
    xvs = math.cos(Es * RAD) - 0.016709
    yvs = math.sqrt(1 - 0.016709 ** 2) * math.sin(Es * RAD)
    rs = math.hypot(xvs, yvs)
    lons = _norm(math.atan2(yvs, xvs) * DEG + ws)
    xs, ys = rs * math.cos(lons * RAD), rs * math.sin(lons * RAD)
    xg, yg, zg = xh + xs, yh + ys, zh
    obl = 23.4393 - 3.563e-7 * d
    ra, dec = _to_radec(*_ecl_to_eq(xg, yg, zg, obl))
    dist = math.sqrt(xg * xg + yg * yg + zg * zg)
    return ra, dec, dist, r


def _giant_perturb(name: str, d: float, xh: float, yh: float, zh: float):
    """Jupiter/Saturn/Uranus mutual perturbations — up to ~0.5 deg if skipped."""
    Mj = _norm(19.8950 + 0.0830853001 * d)
    Msa = _norm(316.9670 + 0.0334442282 * d)
    Mu = _norm(142.5905 + 0.011725806 * d)
    lon = _norm(math.atan2(yh, xh) * DEG)
    lat = math.atan2(zh, math.hypot(xh, yh)) * DEG
    r = math.sqrt(xh * xh + yh * yh + zh * zh)
    if name == "Jupiter":
        lon += (-0.332 * math.sin((2 * Mj - 5 * Msa - 67.6) * RAD)
                - 0.056 * math.sin((2 * Mj - 2 * Msa + 21) * RAD)
                + 0.042 * math.sin((3 * Mj - 5 * Msa + 21) * RAD)
                - 0.036 * math.sin((Mj - 2 * Msa) * RAD)
                + 0.022 * math.cos((Mj - Msa) * RAD)
                + 0.023 * math.sin((2 * Mj - 3 * Msa + 52) * RAD)
                - 0.016 * math.sin((Mj - 5 * Msa - 69) * RAD))
    elif name == "Saturn":
        lon += (0.812 * math.sin((2 * Mj - 5 * Msa - 67.6) * RAD)
                - 0.229 * math.cos((2 * Mj - 4 * Msa - 2) * RAD)
                + 0.119 * math.sin((Mj - 2 * Msa - 3) * RAD)
                + 0.046 * math.sin((2 * Mj - 6 * Msa - 69) * RAD)
                + 0.014 * math.sin((Mj - 3 * Msa + 32) * RAD))
        lat += (-0.020 * math.cos((2 * Mj - 4 * Msa - 2) * RAD)
                + 0.018 * math.sin((2 * Mj - 6 * Msa - 49) * RAD))
    else:
        lon += (0.040 * math.sin((Msa - 2 * Mu + 6) * RAD)
                + 0.035 * math.sin((Msa - 3 * Mu + 33) * RAD)
                - 0.015 * math.sin((Mj - Mu + 20) * RAD))
    cl = math.cos(lat * RAD)
    return (r * cl * math.cos(lon * RAD), r * cl * math.sin(lon * RAD), r * math.sin(lat * RAD))


def precess(ra: float, dec: float, d: float, to_date: bool = True):
    """Rotate between J2000 and the mean equinox of date (Meeus ch. 21).

    The star catalogue is J2000; hour angles are measured from the equinox of
    date. Skipping this leaves every star ~22 arcmin out by 2026, which is a
    systematic smear the whole chart shares, so it looks like a projection bug
    rather than a frame bug.
    """
    t = (d - 0.5) / 36525.0          # d is days from 2000 Jan 0.0 -> J2000 = d 0.5
    if not to_date:
        t = -t
    S = 1.0 / 3600.0
    zeta = (2306.2181 * t + 0.30188 * t * t + 0.017998 * t ** 3) * S
    z = (2306.2181 * t + 1.09468 * t * t + 0.018203 * t ** 3) * S
    theta = (2004.3109 * t - 0.42665 * t * t - 0.041833 * t ** 3) * S
    a = (ra + zeta) * RAD
    dr = dec * RAD
    th = theta * RAD
    A = math.cos(dr) * math.sin(a)
    B = math.cos(th) * math.cos(dr) * math.cos(a) - math.sin(th) * math.sin(dr)
    C = math.sin(th) * math.cos(dr) * math.cos(a) + math.cos(th) * math.sin(dr)
    return _norm(math.atan2(A, B) * DEG + z), math.asin(max(-1.0, min(1.0, C))) * DEG
