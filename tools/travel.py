"""Travel-time estimate between two addresses.

    python3 tools/travel.py estimate --to "465 Huntington Ave, Boston, MA" [--from "<address>"]

Default origin is the home address in the profile. Method (recorded in
DECISIONS.md): geocode both addresses, take the straight-line distance, then
walking at 13 min/km when the trip is 1.2 km or less, otherwise a transit
estimate of 8 + 4.5 min per km. It is a documented approximation, not a route.

Geocoding uses OpenStreetMap Nominatim (1 request/s, with a User-Agent) and
caches results in state/geocache.json. In fixture mode the network is never
used: only the case's pre-filled geocache.json is consulted, and an unknown
address falls back to a default of 30 minutes with a warning.

If GOOGLE_MAPS_API_KEY is set (live/dry), a Routes API transit estimate is
attempted first; on any failure the method above is used.
"""

from __future__ import annotations

import argparse
import math
import os
import time

import _common as c

WALK_MAX_KM = 1.2
WALK_MIN_PER_KM = 13.0
TRANSIT_BASE_MIN = 8.0
TRANSIT_MIN_PER_KM = 4.5
DEFAULT_UNKNOWN_MIN = 30


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def minutes_from_km(km: float) -> tuple[int, str]:
    if km <= WALK_MAX_KM:
        return math.ceil(km * WALK_MIN_PER_KM), "walk"
    return math.ceil(TRANSIT_BASE_MIN + TRANSIT_MIN_PER_KM * km), "transit_estimate"


def load_caches() -> tuple[dict, dict]:
    """Returns (read-only fixture cache, writable state cache)."""
    fixture = c.load_json(c.fixture_path("geocache.json"), default={}) if c.MODE == "fixture" else {}
    state = c.load_json(c.state_path("state/geocache.json"), default={})
    return fixture, state


def geocode(address: str, fixture: dict, state: dict) -> dict | None:
    key = c.norm(address)
    if key in fixture:
        return {**fixture[key], "cached": True}
    if key in state:
        return {**state[key], "cached": True}
    if c.MODE == "fixture":
        return None  # never touch the network in fixture mode
    import requests

    time.sleep(1.0)  # Nominatim usage policy: at most one request per second
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": address, "format": "json", "limit": 1},
                         headers={"User-Agent": "Curator/0.1 (personal events assistant)"}, timeout=15)
        r.raise_for_status()
        hits = r.json()
    except Exception as e:  # network errors are reported, not fatal
        return {"error": f"geocoding failed: {e.__class__.__name__}"}
    if not hits:
        return None
    hit = {"lat": float(hits[0]["lat"]), "lon": float(hits[0]["lon"]), "display": hits[0].get("display_name", address),
           "at": c.now().isoformat()}
    state[key] = hit
    c.write_json_atomic(c.state_path("state/geocache.json"), state)
    return {**hit, "cached": False}


def google_routes_minutes(origin: str, dest: str) -> int | None:
    """Optional upgrade path. Returns None when unavailable or on any error."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key or c.MODE == "fixture":
        return None
    import requests

    try:
        r = requests.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            json={"origin": {"address": origin}, "destination": {"address": dest}, "travelMode": "TRANSIT"},
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.duration"}, timeout=15)
        r.raise_for_status()
        seconds = int(r.json()["routes"][0]["duration"].rstrip("s"))
        return math.ceil(seconds / 60)
    except Exception:
        return None


def estimate(dest: str, origin: str | None = None) -> dict:
    profile = c.load_yaml(c.profile_path(), default={}) or {}
    origin = origin or profile.get("home_address")
    if not origin:
        return {"ok": False, "error": "no origin: pass --from or set home_address in the profile"}
    g = google_routes_minutes(origin, dest)
    if g is not None:
        return {"ok": True, "minutes": g, "method": "google_routes_transit", "from": origin, "to": dest}
    fixture, state = load_caches()
    a, b = geocode(origin, fixture, state), geocode(dest, fixture, state)
    problems = [x["error"] for x in (a, b) if x and "error" in x]
    if problems:
        return {"ok": False, "error": "; ".join(problems), "from": origin, "to": dest}
    if not a or not b:
        missing = [addr for addr, hit in ((origin, a), (dest, b)) if not hit]
        return {"ok": True, "minutes": DEFAULT_UNKNOWN_MIN, "method": "default_unknown_address",
                "warning": f"could not geocode: {missing}; using default {DEFAULT_UNKNOWN_MIN} min",
                "from": origin, "to": dest}
    km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    minutes, method = minutes_from_km(km)
    return {"ok": True, "minutes": minutes, "km": round(km, 2), "method": method, "from": origin, "to": dest,
            "from_geo": {"lat": a["lat"], "lon": a["lon"]}, "to_geo": {"lat": b["lat"], "lon": b["lon"]}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("estimate")
    p.add_argument("--to", required=True)
    p.add_argument("--from", dest="origin")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.verb == "selftest":
        km = haversine_km(42.3620, -71.0842, 42.3394, -71.0940)  # Kendall Sq -> MFA
        assert 2.4 < km < 2.8, km
        assert minutes_from_km(0.5) == (7, "walk")
        assert minutes_from_km(km)[1] == "transit_estimate"
        c.out({"ok": True, "checks": 3, "kendall_to_mfa_km": round(km, 2), "minutes": minutes_from_km(km)[0]})
    else:
        result = estimate(a.to, a.origin)
        c.out({**result, **c.context_summary()}, exit_code=0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
