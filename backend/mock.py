"""
Placeholder payloads for /api/spectrum and /api/detections until the real science code lands.
Everything returned here carries "source": "mock". Shapes follow docs/api.md.
"""
from __future__ import annotations

import math


def spectrum(ra, dec, slug=None):
    """Smooth fake brown-dwarf-like SED: rises to 4.6 um with a CH4 dip near 3.3 um."""
    pts = []
    dates = ["2025-05-05", "2025-11-05", "2026-05-05", "2026-10-29"]
    for i in range(102):
        wl = 0.75 * (5.0 / 0.75) ** (i / 101)
        det = min(6, 1 + int((wl - 0.75) / (5.0 - 0.75) * 6))
        f = 0.05 + 0.4 * math.exp(-((wl - 4.6) / 0.5) ** 2) + 0.12 * math.exp(-((wl - 1.25) / 0.15) ** 2)
        f *= 1 - 0.6 * math.exp(-((wl - 3.3) / 0.25) ** 2)
        pts.append({"wavelength_um": round(wl, 3), "flux_mjy": round(f, 4), "err_mjy": round(0.02 + 0.08 * f, 4),
                    "date": dates[i % 4], "detector": det, "flagged": i % 37 == 0})
    lc = [{"date": d, "mjd": m, "flux_mjy": round(v, 3), "err_mjy": 0.03, "detector": 0}
          for d, m, v in zip(dates, [60800.3, 60984.3, 61165.3, 61342.3], [0.41, 0.55, 0.33, 0.47])]
    return {"ra": ra, "dec": dec, "name": slug, "source": "mock",
            "note": "Placeholder until real aperture photometry is wired in.",
            "points": pts, "light_curve": lc}


def detections(ra, dec, fov, manifest=None):
    cands = []
    if manifest:
        vis = [v for v in manifest["visits"] if v["detector"] == 0 and v.get("predicted")]
        if vis:
            p = vis[-1]["predicted"]
            cands.append({"ra": p["ra"], "dec": p["dec"], "fx": p["fx"], "fy": p["fy"], "score": 0.9,
                          "kind": "mover", "known_match": manifest.get("name"),
                          "pm_mas_yr": manifest.get("pm_mas_yr")})
    return {"ra": ra, "dec": dec, "fov": fov, "source": "mock",
            "note": "Placeholder: marks the predicted target position, no detection model yet.",
            "candidates": cands, "variability": []}
