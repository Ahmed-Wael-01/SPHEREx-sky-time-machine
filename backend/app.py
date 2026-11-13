"""
SPHEREx Sky Time Machine - Flask API.

    cd backend && flask --app app run --debug --port 5000

Endpoints (contract in docs/api.md):
    GET /api/health
    GET /api/targets
    GET /api/frames?ra=&dec=&fov=[&target=]
    GET /api/spectrum?ra=&dec=[&target=]
    GET /api/detections?ra=&dec=&fov=[&target=]
    GET /data/<path>          baked PNGs / manifests (same files the static frontend serves)

Today every endpoint answers from pre-baked targets (science/fetch_cutouts.py output).
Responses carry "source": "prebaked" | "mock" so nobody mistakes placeholder data for real data.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory
import requests

from cache import cache
import mock

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "frontend" / "public" / "data")).resolve()

app = Flask(__name__)


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = os.environ.get("CORS_ORIGIN", "*")
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


class BadRequest(Exception):
    pass


class NotBaked(Exception):
    pass


@app.errorhandler(NotBaked)
def not_baked(e):
    return jsonify({"error": "not_baked", "message": str(e),
                    "targets": [t["target"] for t in baked_index()]}), 404


@app.errorhandler(BadRequest)
def bad_request(e):
    return jsonify({"error": "bad_request", "message": str(e)}), 400


# --------------------------------------------------------------------------- helpers

def arg_float(name, default=None, lo=None, hi=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        if default is None:
            raise BadRequest(f"missing parameter '{name}'")
        return default
    try:
        v = float(raw)
    except ValueError:
        raise BadRequest(f"'{name}' must be a number in degrees, got {raw!r}")
    if not math.isfinite(v) or (lo is not None and v < lo) or (hi is not None and v > hi):
        raise BadRequest(f"'{name}' out of range [{lo}, {hi}]: {v}")
    return v


def sep_deg(ra1, dec1, ra2, dec2):
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def baked_index():
    f = DATA_DIR / "index.json"
    return json.loads(f.read_text()) if f.exists() else []


def load_manifest(slug):
    f = DATA_DIR / slug / "manifest.json"
    if not f.exists():
        return None
    return cache.get_or_set(f"manifest:{slug}:{f.stat().st_mtime}", lambda: json.loads(f.read_text()))


def find_target(ra, dec, fov):
    """Nearest baked target whose centre lies within the requested field (min 0.05 deg)."""
    best, best_sep = None, None
    for t in baked_index():
        if t["target"] == "mock":
            continue
        s = sep_deg(ra, dec, t["ra"], t["dec"])
        if s <= max(fov / 2, 0.05) and (best_sep is None or s < best_sep):
            best, best_sep = t["target"], s
    return best


def position_args(need_fov=False):
    slug = request.args.get("target")
    ra = arg_float("ra", None if not slug else 0.0, 0, 360)
    dec = arg_float("dec", None if not slug else 0.0, -90, 90)
    fov = arg_float("fov", 0.2, 0.01, 2.0) if need_fov else None
    if slug and not (DATA_DIR / slug / "manifest.json").exists():
        raise NotBaked(f"Target '{slug}' has not been processed yet. Run science/fetch_cutouts.py --target {slug}.")
    if not slug:
        slug = find_target(ra, dec, fov or 0.2)
    return slug, ra, dec, fov


# --------------------------------------------------------------------------- routes

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "data_dir": str(DATA_DIR), "targets": [t["target"] for t in baked_index()],
                    "cache": cache.kind})


@app.get("/api/targets")
def targets():
    return jsonify(baked_index())


@app.get("/api/frames")
def frames():
    slug, ra, dec, fov = position_args(need_fov=True)
    if slug is None:
        return jsonify({"error": "not_baked", "ra": ra, "dec": dec, "fov": fov,
                        "message": "No pre-processed SPHEREx frames for this position yet. "
                                   "Live mode (any coordinates) is a stretch goal; try a test target "
                                   "or ?target=mock.", "targets": [t["target"] for t in baked_index()]}), 404
    m = load_manifest(slug)
    return jsonify(m)


NEAR_ARCSEC = 30  # a measured spectrum describes the target; show it only for clicks this close to it


@app.get("/api/spectrum")
def spectrum():
    slug, ra, dec, _ = position_args()
    if slug == "mock":
        return jsonify(mock.spectrum(ra, dec, slug))
    empty = {"ra": ra, "dec": dec, "source": "none", "points": [], "light_curve": []}
    f = DATA_DIR / slug / "spectrum.json" if slug else None
    if f is None or not f.exists():  # never invent points: real data only
        return jsonify({**empty, "note": "This target's spectrum has not been measured yet." if slug
                        else "No measured spectrum at this position."})
    s = json.loads(f.read_text())  # written by science/make_spectrum.py
    spots = s.get("positions") or [[s["ra"], s["dec"]]]
    if "ra" in request.args and not any(sep_deg(ra, dec, a, d) * 3600 <= NEAR_ARCSEC for a, d in spots):
        return jsonify({**empty, "note": f"Click the target itself: measured spectra exist for "
                                         f"{s.get('label', slug)} only (measuring any spot on click is the next step)."})
    return jsonify(s)


@app.get("/api/detections")
def detections():
    slug, ra, dec, fov = position_args(need_fov=True)
    if slug:
        f = DATA_DIR / slug / "detections.json"
        if f.exists():  # written by Remon / Fatma's models
            return jsonify(json.loads(f.read_text()))
    return jsonify(mock.detections(ra, dec, fov, load_manifest(slug) if slug else None))


@app.get("/api/simbad")
def simbad_lookup():
    """Live SIMBAD astronomical object cross-identification via Harvard mirror."""
    try:
        ra = float(request.args.get("ra", 0))
        dec = float(request.args.get("dec", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid coordinates"}), 400

    url = f"https://simbad.harvard.edu/simbad/sim-coo?Coord={ra}+{dec}&Radius=0.8&Radius.unit=arcmin&output.format=ASCII"
    try:
        r = requests.get(url, timeout=3.5)
        text = r.text
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        match_info = None
        for line in lines:
            if line.startswith("Object "):
                parts = [p.strip() for p in line.split("---")]
                name = parts[0].replace("Object ", "").strip()
                otype = parts[1].strip() if len(parts) > 1 else "Astronomical Object"
                match_info = {
                    "match": True,
                    "identifier": name,
                    "otype": otype,
                    "sp_type": "",
                    "dist_arcsec": 0.0,
                    "url": f"https://simbad.harvard.edu/simbad/sim-id?Ident={requests.utils.quote(name)}"
                }
                break
            elif "|" in line and not line.startswith("#") and not line.startswith("-") and not line.startswith("="):
                cols = [c.strip() for c in line.split("|")]
                if len(cols) >= 4 and cols[0].isdigit():
                    dist = float(cols[1]) if cols[1] != "~" else 0.0
                    ident = cols[2].replace("NAME ", "").strip()
                    typ = cols[3]
                    sp = cols[10] if len(cols) > 10 and cols[10] != "~" else ""
                    match_info = {
                        "match": True,
                        "identifier": ident,
                        "otype": typ,
                        "sp_type": sp,
                        "dist_arcsec": dist,
                        "url": f"https://simbad.harvard.edu/simbad/sim-id?Ident={requests.utils.quote(ident)}"
                    }
                    break

        if match_info:
            return jsonify(match_info)

        # "No match" is common for faint sources and is not evidence of anything new.
        return jsonify({
            "match": False,
            "message": "No SIMBAD object within 0.8 arcmin.",
        })
    except Exception as e:
        # unreachable / timeout: say so, never report it as "no match"
        return jsonify({"match": None, "error": str(e), "message": "SIMBAD lookup unavailable right now."})


@app.get("/data/<path:path>")
def data_files(path):
    if ".." in Path(path).parts:
        abort(404)
    return send_from_directory(DATA_DIR, path, max_age=3600)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
