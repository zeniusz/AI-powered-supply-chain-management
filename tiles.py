"""Map tile provider: OpenStreetMap by default, CARTO Voyager when CARTO_API_KEY is set. The key is separate from OPENAI_API_KEY."""
from __future__ import annotations

import os
import time
import urllib.request

OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
CARTO_ATTRIBUTION = OSM_ATTRIBUTION + ' &copy; <a href="https://carto.com/attributions">CARTO</a>'
PROBE_TILE = "6/33/21"  # central Europe land tile; CARTO's "API KEY REQUIRED" placeholder is only ~2 KB
MIN_REAL_TILE_BYTES = 3000
_cache: dict = {}


def provider() -> dict:
    key = os.getenv("CARTO_API_KEY", "")
    if key:
        base = "https://basemaps.cartocdn.com/rastertiles/voyager/"
        return {"id": "carto", "name": "CARTO Voyager", "attribution": CARTO_ATTRIBUTION, "url": base + "{z}/{x}/{y}.png?key=" + key,
                "probe": base + PROBE_TILE + ".png?key=" + key}
    return {"id": "osm", "name": "OpenStreetMap", "attribution": OSM_ATTRIBUTION, "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "probe": "https://tile.openstreetmap.org/" + PROBE_TILE + ".png"}


def probe(p: dict) -> tuple[bool, str]:
    """Fetch one known land tile server-side (cached 5 min) so an unreachable or placeholder provider is reported."""
    hit = _cache.get(p["id"])
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    request = urllib.request.Request(p["probe"], headers={"User-Agent": "ThreadlineOps/1.0 (portfolio demo)"})
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            body, is_image = resp.read(), resp.headers.get("Content-Type", "").startswith("image/")
        if not is_image or len(body) < MIN_REAL_TILE_BYTES:
            result = (False, "CARTO returned a placeholder tile. Check that CARTO_API_KEY is a valid Basemaps key." if p["id"] == "carto"
                      else "OpenStreetMap returned an unexpected tile response.")
        else:
            result = (True, "")
    except Exception as exc:
        result = (False, f"{p['name']} map tiles could not be reached ({type(exc).__name__}).")
    _cache[p["id"]] = (time.time(), result)
    return result


def config() -> dict:
    p = provider()
    ok, message = probe(p)
    return {"name": p["name"], "url": p["url"], "attribution": p["attribution"], "ok": ok, "message": message}
