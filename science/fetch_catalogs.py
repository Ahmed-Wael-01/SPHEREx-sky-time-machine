#!/usr/bin/env python3
"""
Download Gaia DR3 and AllWISE sources around a baked target, for the overlay chips in the player.

    python science/fetch_catalogs.py --target wise0855
    python science/fetch_catalogs.py --all

Reads frontend/public/data/<slug>/manifest.json (centre + field) and writes catalogs.json next to it:
  {"gaia":    {"epoch": 2016.0, "source": "...", "cols": ["ra","dec","pmra","pmdec","g"],  "rows": [[...], ...]},
   "allwise": {"epoch": 2010.5, "source": "...", "cols": ["ra","dec","w1","w2"],             "rows": [[...], ...]}}
The player moves Gaia stars to each frame's date with their proper motion.
Fetch_cutouts.py calls this automatically after a bake (skip with --no-catalogs).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB_DATA = REPO / "frontend" / "public" / "data"
MAX_ROWS = 3000


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _num(v, nd=None):
    try:
        if v is None or hasattr(v, "mask") and v.mask:
            return None
        f = float(v)
        if not math.isfinite(f):
            return None
        return round(f, nd) if nd is not None else f
    except (TypeError, ValueError):
        return None


def _col(tab, name):
    cols = {c.lower(): c for c in tab.colnames}
    return tab[cols[name.lower()]]


def gaia(ra, dec, radius):
    cone = f"1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius}))"
    attempts = [
        ("ESA Gaia archive", "gaiadr3.gaia_source", "astroquery.gaia"),
        ("IRSA", "gaia_dr3_source", "irsa"),
    ]
    for label, table, how in attempts:
        q = (f"SELECT TOP {MAX_ROWS} ra, dec, pmra, pmdec, phot_g_mean_mag FROM {table} "
             f"WHERE {cone} AND phot_g_mean_mag < 20.5 ORDER BY phot_g_mean_mag")
        try:
            if how == "astroquery.gaia":
                from astroquery.gaia import Gaia
                tab = Gaia.launch_job(q).get_results()
            else:
                from astroquery.ipac.irsa import Irsa
                tab = Irsa.query_tap(q).to_table()
            rows = [[_num(a, 6), _num(b, 6), _num(c, 2) or 0.0, _num(d, 2) or 0.0, _num(g, 2)]
                    for a, b, c, d, g in zip(_col(tab, "ra"), _col(tab, "dec"), _col(tab, "pmra"),
                                             _col(tab, "pmdec"), _col(tab, "phot_g_mean_mag"))]
            log(f"  Gaia DR3: {len(rows)} sources via {label}")
            return {"epoch": 2016.0, "source": f"Gaia DR3 ({label})", "cols": ["ra", "dec", "pmra", "pmdec", "g"],
                    "rows": rows}
        except Exception as e:
            log(f"  Gaia via {label} failed: {e!r}")
    return None


def allwise(ra, dec, radius):
    q = (f"SELECT TOP {MAX_ROWS} ra, dec, w1mpro, w2mpro FROM allwise_p3as_psd "
         f"WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius})) = 1 ORDER BY w2mpro")
    try:
        from astroquery.ipac.irsa import Irsa
        tab = Irsa.query_tap(q).to_table()
        rows = [[_num(a, 6), _num(b, 6), _num(c, 2), _num(d, 2)]
                for a, b, c, d in zip(_col(tab, "ra"), _col(tab, "dec"), _col(tab, "w1mpro"), _col(tab, "w2mpro"))]
        log(f"  AllWISE: {len(rows)} sources via IRSA")
        return {"epoch": 2010.5, "source": "AllWISE (IRSA)", "cols": ["ra", "dec", "w1", "w2"], "rows": rows}
    except Exception as e:
        log(f"  AllWISE via IRSA failed: {e!r}")
        return None


def run(slug):
    mf = WEB_DATA / slug / "manifest.json"
    if not mf.exists():
        log(f"  {slug}: no manifest, bake it first")
        return False
    m = json.loads(mf.read_text())
    span = m["pixels"] * m["pixel_scale_arcsec"] / 3600
    radius = round(span * 0.75, 4)  # covers the corners of the square frame
    log(f"== catalogues for {slug}: r = {radius} deg around {m['ra']:.5f} {m['dec']:+.5f}")
    out = {}
    g = gaia(m["ra"], m["dec"], radius + 0.01)  # margin for proper motion since 2016
    if g:
        out["gaia"] = g
    w = allwise(m["ra"], m["dec"], radius)
    if w:
        out["allwise"] = w
    if not out:
        log("  nothing retrieved; overlays stay off for this target")
        return False
    (WEB_DATA / slug / "catalogs.json").write_text(json.dumps(out, separators=(",", ":")))
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target")
    g.add_argument("--all", action="store_true")
    a = p.parse_args()
    slugs = [d.name for d in sorted(WEB_DATA.iterdir()) if (d / "manifest.json").exists() and d.name != "mock"] \
        if a.all else [a.target]
    for s in slugs:
        run(s)


if __name__ == "__main__":
    main()
