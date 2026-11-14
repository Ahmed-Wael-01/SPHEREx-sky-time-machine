#!/usr/bin/env python3
"""
Spectrum + light curve of a target from the photos we already downloaded (no new download).

    python science/make_spectrum.py --target wise0855          # one target
    python science/make_spectrum.py --all                      # every target whose photos are on this machine

Writes frontend/public/data/<target>/spectrum.json (the format in docs/api.md), which the website shows
when you click the target, and science/output/<target>/spectrum.png for a quick look.

How it measures, per photo (each SPHEREx photo sees the target in one colour, so 300 photos = 300 colours):
  1. Where is the target on that date? Catalogue position + proper motion (same as the viewer's circle).
     Stars that don't move (RW Aur, R Dra) are re-centred on their brightest pixel, within 1 pixel.
  2. Brightness = light inside a 2-pixel circle minus the sky measured in a ring 4-7 pixels out,
     converted from MJy/sr to milli-Jansky with the pixel's size on the sky.
  3. If a Gaia star sits within 15" (WISE 0855 has one ~8" away), both are fitted together with the same
     star shape so the neighbour's light is not counted ("deblending").
  4. Points are flagged when a pixel in the circle is marked bad, overloaded (OVERFLOW/NONLINEAR) or missing.
Light curve: for each sky pass, the average brightness in one fixed colour range, so dates are compared
like with like.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fetch_cutouts import (CACHE, DEFAULT_MASK, REPO, SCI_OUT, WEB_DATA, flag_bits,  # noqa: E402
                           mjd_to_date, mjd_to_year, propagate)

AP_R = 2.0          # aperture radius, pixels (~12"); same as Alaa's quickstart, matches WISE W1/W2 calibration
ANN = (4.0, 7.0)    # sky ring, pixels
NEIGHBOUR_ARCSEC = 15.0
SATURATION = ["OVERFLOW", "NONLINEAR"]
GLOW_RINGS = [(2, 4), (4, 7), (7, 10), (10, 14)]  # pixels; first one mostly outside an overloaded core
# light-curve colour ranges to try, best first: (label, lo um, hi um)
LC_BANDS = [("4.4-5.0 um", 4.4, 5.0), ("3.8-4.4 um", 3.8, 4.4), ("2.4-3.8 um", 2.4, 3.8),
            ("1.6-2.4 um", 1.6, 2.4), ("1.1-1.6 um", 1.1, 1.6), ("0.75-1.1 um", 0.75, 1.1)]


# ------------------------------------------------------------------ geometry helpers

def aperture_weights(shape, x, y, r, sub=5):
    """Fraction of each pixel inside a circle (supersampled), in a box around (x, y)."""
    ny, nx = shape
    x0, x1 = max(0, int(math.floor(x - r - 1))), min(nx, int(math.ceil(x + r + 2)))
    y0, y1 = max(0, int(math.floor(y - r - 1))), min(ny, int(math.ceil(y + r + 2)))
    off = (np.arange(sub) + 0.5) / sub - 0.5
    yy, xx = np.mgrid[y0:y1, x0:x1]
    w = np.zeros(xx.shape)
    for dy in off:
        for dx in off:
            w += ((xx + dx - x) ** 2 + (yy + dy - y) ** 2) <= r * r
    return (slice(y0, y1), slice(x0, x1)), w / sub ** 2


def ring(shape, x, y, r_in, r_out):
    ny, nx = shape
    x0, x1 = max(0, int(x - r_out - 1)), min(nx, int(x + r_out + 2))
    y0, y1 = max(0, int(y - r_out - 1)), min(ny, int(y + r_out + 2))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d2 = (xx - x) ** 2 + (yy - y) ** 2
    return (slice(y0, y1), slice(x0, x1)), (d2 >= r_in ** 2) & (d2 <= r_out ** 2)


def clipped_median(v):
    v = v[np.isfinite(v)]
    if v.size < 8:
        return np.nan, np.nan
    for _ in range(5):
        med, sd = np.median(v), 1.4826 * np.median(np.abs(v - np.median(v)))
        keep = np.abs(v - med) < 3 * max(sd, 1e-12)
        if keep.all():
            break
        v = v[keep]
    return float(np.median(v)), float(1.4826 * np.median(np.abs(v - np.median(v))) / math.sqrt(max(v.size, 1)))


def gauss(shape, x, y, sig):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sig ** 2)) / (2 * np.pi * sig ** 2)


def linfit(img, var, models):
    ok = np.isfinite(img) & np.isfinite(var) & (var > 0)
    if ok.sum() < len(models) + 5:
        return None
    A = np.column_stack([m[ok] for m in models] + [np.ones(ok.sum())])
    w = 1 / np.sqrt(var[ok])
    Aw = A * w[:, None]
    coef, *_ = np.linalg.lstsq(Aw, img[ok] * w, rcond=None)
    cov = np.linalg.pinv(Aw.T @ Aw)
    chi2 = float((((A @ coef - img[ok]) * w) ** 2).sum())
    return coef, np.sqrt(np.clip(np.diag(cov), 0, None)), chi2


# ------------------------------------------------------------------ one photo

def measure(path, ra, dec, recentre, neighbours, mask_names):
    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning
    from astropy.wcs.utils import proj_plane_pixel_area
    warnings.simplefilter("ignore", FITSFixedWarning)
    with fits.open(path, memmap=False) as h:
        names = [x.name for x in h]
        hdr = h["IMAGE"].header
        img = h["IMAGE"].data.astype(float)
        if "ZODI" in names:
            img = img - h["ZODI"].data.astype(float)
        var = h["VARIANCE"].data.astype(float) if "VARIANCE" in names else np.ones_like(img)
        flags = h["FLAGS"].data.astype(np.int64) if "FLAGS" in names else np.zeros(img.shape, np.int64)
        bits = flag_bits(h["FLAGS"].header) if "FLAGS" in names else {}
    wcs = WCS(hdr)
    to_mjy = proj_plane_pixel_area(wcs) * (math.pi / 180) ** 2 * 1e9  # MJy/sr per pixel -> mJy
    x, y = (float(v) for v in wcs.world_to_pixel_values(ra, dec))
    ny, nx = img.shape
    if not (ANN[1] + 2 < x < nx - ANN[1] - 3 and ANN[1] + 2 < y < ny - ANN[1] - 3):
        return None
    bad_bits = sum(1 << bits[n] for n in mask_names if n in bits)
    sat_bits = sum(1 << bits[n] for n in SATURATION if n in bits)
    bad = ((flags & bad_bits) != 0) | ~np.isfinite(img) | ~np.isfinite(var) | (var <= 0)
    img = np.where(bad, np.nan, img)

    sl, rmask = ring(img.shape, x, y, *ANN)
    sky, sky_err = clipped_median(img[sl][rmask])
    if not np.isfinite(sky):
        return None
    if recentre:  # catalogue position rounded to ~4": move to the brightest pixel within 1 px, if it's a clear peak
        xi, yi = int(round(x)), int(round(y))
        cut = img[yi - 1:yi + 2, xi - 1:xi + 2] - sky
        if np.isfinite(cut).all() and cut.max() > 5 * math.sqrt(np.nanmedian(var[yi - 1:yi + 2, xi - 1:xi + 2])):
            w = np.clip(cut, 0, None)
            yy, xx = np.mgrid[-1:2, -1:2]
            x, y = xi + float((w * xx).sum() / w.sum()), yi + float((w * yy).sum() / w.sum())

    asl, aw = aperture_weights(img.shape, x, y, AP_R)
    a_img, a_var = img[asl], var[asl]
    inside = aw > 0
    missing = float((aw * ~np.isfinite(a_img)).sum() / aw.sum())
    if missing > 0.25:
        return wings(img, var, x, y, to_mjy)
    filled = np.where(np.isfinite(a_img), a_img, sky)
    flux = float((aw * (filled - sky)).sum())
    err = math.sqrt(float((aw ** 2 * np.where(np.isfinite(a_var), a_var, 0)).sum()) + (aw.sum() * sky_err) ** 2)
    a_flags = flags[asl][inside]
    saturated = bool((a_flags & sat_bits).any())
    flagged = saturated or missing > 0 or bool(((flags[asl] & bad_bits) != 0)[inside].any())
    method = "aperture"

    # deblend from Gaia neighbours within 15"
    near = []
    for nra, ndec in neighbours:
        xn, yn = (float(v) for v in wcs.world_to_pixel_values(nra, ndec))
        if math.hypot(xn - x, yn - y) * 6.15 <= NEIGHBOUR_ARCSEC:
            near.append((xn, yn))
    if near and not saturated:
        R = 5
        xi, yi = int(round(x)), int(round(y))
        if R <= xi < nx - R and R <= yi < ny - R:
            box = (slice(yi - R, yi + R + 1), slice(xi - R, xi + R + 1))
            bi, bv = img[box] - sky, var[box]
            xs, ys = x - (xi - R), y - (yi - R)
            pts = [(xs, ys)] + [(xn - (xi - R), yn - (yi - R)) for xn, yn in near]
            best = None
            for sig in np.linspace(0.6, 1.8, 13):  # one shared star shape; the brighter source sets its width
                fit = linfit(bi, bv, [gauss(bi.shape, px, py, sig) for px, py in pts])
                if fit and (best is None or fit[2] < best[1][2]):
                    best = (sig, fit)
            if best:
                coef, cerr, _ = best[1]
                flux, err, method = float(coef[0]), float(cerr[0]), "deblended"
    return {"flux_mjy": flux * to_mjy, "err_mjy": err * to_mjy, "flagged": flagged,
            "saturated": saturated, "method": method, "x": round(x, 2), "y": round(y, 2)}


def wings(img, var, x, y, to_mjy):
    """The core is blank (too bright for the camera: NASA's file has no value there). Measure the glow around
    it instead, in rings 2-4, 4-7, 7-10 and 10-14 px from the centre, each with the sky just beyond. Not the
    total brightness, but it rises and falls with the star. The brighter the star, the bigger the blank core,
    so run() later picks ONE ring that works on almost every photo and uses it for all of them (otherwise
    bright dates would be measured further out and look fainter). Always flagged."""
    rings = {}
    for r_in, r_out in GLOW_RINGS:
        sl, rm = ring(img.shape, x, y, r_in, r_out)
        vals, vv = img[sl][rm], var[sl][rm]
        ok = np.isfinite(vals)
        ssl, srm = ring(img.shape, x, y, r_out + 4, r_out + 9)
        sky, sky_err = clipped_median(img[ssl][srm])
        if ok.mean() < 0.7 or not np.isfinite(sky):
            continue
        scale = rm.sum() / ok.sum()  # make up for blank pixels in the ring
        flux = float((vals[ok] - sky).sum() * scale)
        err = math.sqrt(float(np.nansum(vv[ok])) * scale ** 2 + (rm.sum() * sky_err) ** 2)
        rings[f"{r_in:g}-{r_out:g} px"] = (flux * to_mjy, err * to_mjy)
    if not rings:
        return None
    first = next(iter(rings))
    return {"flux_mjy": rings[first][0], "err_mjy": rings[first][1], "flagged": True, "saturated": True,
            "method": f"glow {first}", "glow_rings": rings, "x": round(x, 2), "y": round(y, 2)}


MIN_PHOTOS_PER_PASS = 3


def judge(lc, floor, points=None):
    """Is the change between passes bigger than the uncertainty? chi-squared against a constant, using only
    passes measured on at least MIN_PHOTOS_PER_PASS photos. A star overloaded in most photos and measured
    with plain circles (not the glow ring) gets 'inconclusive'."""
    if points:
        n_sat = sum(p.get("saturated") for p in points)
        glow = any(q.get("band", "").find("glow") >= 0 for q in lc)
        if not glow and n_sat > len(points) / 2:
            return {"varies": None, "chi2_per_dof": None, "max_over_min": None, "systematic_floor": floor,
                    "text": f"inconclusive: the star overloads the camera in {n_sat} of {len(points)} photos, "
                            "so the few usable ones cannot show a reliable change"}
    use = [q for q in lc if q.get("n", MIN_PHOTOS_PER_PASS) >= MIN_PHOTOS_PER_PASS]
    if len(use) < 2:
        return {"varies": None, "chi2_per_dof": None, "max_over_min": None, "systematic_floor": floor,
                "text": f"not enough photos per pass for a verdict (need {MIN_PHOTOS_PER_PASS} or more on 2 passes)"}
    f = np.array([q["flux_mjy"] for q in use])
    e = np.array([max(q["err_mjy"], 1e-9) for q in use])
    w = 1 / e ** 2
    mean = float((w * f).sum() / w.sum())
    chi2 = float((((f - mean) / e) ** 2).sum()) / (len(use) - 1)
    ratio = float(f.max() / f.min()) if f.min() > 0 else None
    varies = chi2 > 4
    left = len(lc) - len(use)
    note = f"; {left} pass{'es' if left > 1 else ''} with fewer than {MIN_PHOTOS_PER_PASS} photos not counted" if left else ""
    text = (f"changes between passes are larger than the uncertainty (brightest/faintest = {ratio:.1f}x){note}"
            if varies and ratio else
            f"changes between passes are larger than the uncertainty{note}" if varies else
            "no change beyond the uncertainty (steady within about "
            f"{100 * float(np.median(e / np.abs(f))):.0f}%){note}")
    return {"varies": varies, "chi2_per_dof": round(chi2, 2), "max_over_min": None if ratio is None else round(ratio, 2),
            "systematic_floor": floor, "passes_counted": len(use), "text": text}


def shape_times_level(sel, lo, hi, band, nbins=6, iters=15):
    """Fit flux = S(colour) * A(pass) to points in one band; returns one value per pass = A * mean(S)."""
    edges = np.linspace(lo, hi, nbins + 1)
    wl = np.array([p["wavelength_um"] for p in sel])
    f = np.array([p["flux_mjy"] for p in sel])
    ep = np.array([p["epoch"] for p in sel])
    b = np.clip(np.digitize(wl, edges) - 1, 0, nbins - 1)
    passes = sorted(set(ep.tolist()))
    A = {e: 1.0 for e in passes}
    for _ in range(iters):
        ratio = f / np.array([A[e] for e in ep])
        S_bin = {k: float(np.median(ratio[b == k])) for k in sorted(set(b.tolist()))}
        centres = [float(np.median(wl[b == k])) for k in S_bin]
        S = np.interp(wl, centres, list(S_bin.values()))  # smooth between bins: the band can be steep
        ok = np.abs(S) > 1e-9
        for e in passes:
            m = (ep == e) & ok
            if m.any():
                A[e] = float(np.median(f[m] / S[m]))
        norm = float(np.median(list(A.values()))) or 1.0
        A = {e: a / norm for e, a in A.items()}
    S_mean = float(np.mean(list(S_bin.values())))
    out = []
    for e in passes:
        m = (ep == e) & ok
        if not m.any():
            continue
        r = f[m] / S[m]
        err = (float(np.std(r, ddof=1) / math.sqrt(m.sum())) if m.sum() >= 3 else
               float(np.median([sel[i]["err_mjy"] for i in np.where(m)[0]])) / max(abs(S_mean), 1e-9))
        mjd = float(np.median([sel[i]["mjd"] for i in np.where(m)[0]]))
        out.append({"date": mjd_to_date(mjd), "mjd": round(mjd, 3), "epoch": e,
                    "flux_mjy": round(A[e] * S_mean, 4), "err_mjy": round(abs(err * S_mean), 4),
                    "n": int(m.sum()), "band": band})
    return out


# ------------------------------------------------------------------ one target

def run(slug, mask_names):
    web = WEB_DATA / slug
    man = json.loads((web / "manifest.json").read_text())
    exps = json.loads((web / "exposures.json").read_text())
    cache = CACHE / slug
    have = [e for e in exps if (cache / e["file"]).exists()]
    if not have:
        print(f"{slug}: none of its {len(exps)} photos are on this machine ({cache}); skipped")
        return None
    ra2000, dec2000 = man["ra_j2000"], man["dec_j2000"]
    pmra, pmdec = man["pm_mas_yr"]
    moving = abs(pmra) + abs(pmdec) > 50
    gaia = []
    cat = web / "catalogs.json"
    if cat.exists():
        g = json.loads(cat.read_text()).get("gaia") or {}
        gaia = [(r[0], r[1], r[2] or 0.0, r[3] or 0.0, g.get("epoch", 2016.0)) for r in g.get("rows", [])]
    print(f"{slug}: measuring {len(have)} of {len(exps)} photos"
          f"{' (target moves; following its predicted path)' if moving else ''}")

    points = []
    for i, e in enumerate(have, 1):
        yr = mjd_to_year(e["mjd"])
        ra, dec = propagate(ra2000, dec2000, pmra, pmdec, yr)
        neighbours = []
        for gra, gdec, gpmra, gpmdec, gep in gaia:
            nra = gra + gpmra * (yr - gep) / 3.6e6 / math.cos(math.radians(gdec))
            ndec = gdec + gpmdec * (yr - gep) / 3.6e6
            d = 3600 * math.hypot((nra - ra) * math.cos(math.radians(dec)), ndec - dec)
            if 2.5 < d <= NEIGHBOUR_ARCSEC:  # within 2.5" = the target itself
                neighbours.append((nra, ndec))
        try:
            m = measure(cache / e["file"], ra, dec, not moving, neighbours, mask_names)
        except Exception as ex:  # noqa: BLE001
            print(f"   skipped {e['file']}: {ex!r}")
            m = None
        if m and e.get("wavelength_um"):
            points.append({"wavelength_um": round(e["wavelength_um"], 4),
                           "bandwidth_um": round(e.get("bandwidth_um") or 0, 4),
                           "flux_mjy": round(m["flux_mjy"], 4), "err_mjy": round(m["err_mjy"], 4),
                           "date": mjd_to_date(e["mjd"]), "mjd": round(e["mjd"], 4), "epoch": e["epoch"],
                           "detector": e["detector"], "flagged": m["flagged"], "saturated": m["saturated"],
                           "method": m["method"], "_rings": m.get("glow_rings")})
        if i % 50 == 0:
            print(f"   {i}/{len(have)}")
    if not points:
        print(f"{slug}: no usable measurements")
        return None
    points.sort(key=lambda p: p["wavelength_um"])
    epochs = sorted({p["epoch"] for p in points})

    glow = [p for p in points if p["_rings"]]
    if glow:  # one ring for every glow point: the innermost ring usable on at least 90% of them
        for r_in, r_out in GLOW_RINGS:
            label = f"{r_in:g}-{r_out:g} px"
            if sum(label in p["_rings"] for p in glow) >= 0.9 * len(glow):
                break
        dropped = 0
        for p in glow:
            if label in p["_rings"]:
                f, e = p["_rings"][label]
                p.update(flux_mjy=round(f, 4), err_mjy=round(e, 4), method=f"glow {label}")
            else:
                p["drop"] = True
                dropped += 1
        points = [p for p in points if not p.get("drop")]
        print(f"   glow measured {label} from the centre on every photo ({dropped} photos where that ring is blank dropped)")
    for p in points:
        p.pop("_rings", None)

    # the fit's own error bars ignore how imperfect a simple star shape is; widen them to match the real
    # scatter between photos that saw (almost) the same colour
    good = [p for p in points if not p["flagged"]] or [p for p in points if p["method"].startswith("glow")]
    ratios = []  # same pass AND same colour, so a star that really changes between dates doesn't count as noise
    for ep in epochs:
        for lo in np.arange(0.7, 5.1, 0.1):
            sel = [p for p in good if p["epoch"] == ep and lo <= p["wavelength_um"] < lo + 0.1]
            if len(sel) >= 3:
                ratios.append(np.std([p["flux_mjy"] for p in sel], ddof=1) / np.median([p["err_mjy"] for p in sel]))
    err_scale = max(1.0, float(np.median(ratios))) if ratios else 1.0
    for p in points:
        p["err_mjy"] = round(p["err_mjy"] * err_scale, 4)

    # light curve: one colour range, one value per sky pass. Each pass sees slightly different colours, and
    # the object is brighter at some colours than others, so fit  brightness = shape(colour) x level(pass)
    # inside the band: the shape is shared by all dates, the level is what changes. (Otherwise a pass that
    # happened to see redder colours would look brighter.)
    use_glow = not any(not p["flagged"] for p in points)
    if use_glow:  # all glow points use the same ring (above)
        common = next((p["method"] for p in points if p["method"].startswith("glow")), None)
        lc_pts = [p for p in points if p["method"] == common]
    else:
        lc_pts = [p for p in points if not p["flagged"]]
    best = None
    for label, lo, hi in LC_BANDS:
        sel = [p for p in lc_pts if lo <= p["wavelength_um"] < hi]
        covered = {p["epoch"] for p in sel}
        if len(covered) < 2:
            continue
        f = np.array([p["flux_mjy"] for p in sel])
        snr = float(np.median(f) / max(np.median([p["err_mjy"] for p in sel]), 1e-9))
        if snr < 3:  # too faint here to say anything about changes
            continue
        score = (len(covered), snr)
        if best is None or score > best[0]:
            best = (score, label, lo, hi)
    light_curve, lc_band, variability = [], None, None
    if best:
        _, lc_band, lo, hi = best
        if use_glow:
            lc_band += f", glow around the overloaded core ({common.split(' ', 1)[1]} from the centre)"
        sel = [p for p in lc_pts if lo <= p["wavelength_um"] < hi]
        light_curve = shape_times_level(sel, lo, hi, lc_band)
        # allowance for what the error bars can't see: separating a neighbour with a simple star shape (10%),
        # a glow ring instead of the whole star (5%), plain circle photometry (3%)
        methods = [p["method"] for p in sel]
        floor = (0.10 if methods.count("deblended") > len(methods) / 2 else
                 0.05 if use_glow else 0.03)
        for q in light_curve:
            q["err_mjy"] = round(math.sqrt(q["err_mjy"] ** 2 + (floor * q["flux_mjy"]) ** 2), 4)
        variability = judge(light_curve, floor, points)
        print(f"   variability: {variability['text']}")
    # where the target is on each pass, so the website only shows this spectrum when you click near it
    positions = []
    for ep in epochs:
        mjd = float(np.median([p["mjd"] for p in points if p["epoch"] == ep]))
        pra, pdec = propagate(ra2000, dec2000, pmra, pmdec, mjd_to_year(mjd))
        positions.append([round(pra, 6), round(pdec, 6)])

    n_flag = sum(p["flagged"] for p in points)
    n_sat = sum(p["saturated"] for p in points)
    n_deb = sum(p["method"] == "deblended" for p in points)
    n_glow = sum(p["method"].startswith("glow") for p in points)
    note = (f"{len(points)} measurements, one per SPHEREx photo; {n_flag} flagged"
            + (f" ({n_sat} overloaded: the star is too bright for the camera there)" if n_sat else "")
            + (f"; {n_deb} deblended from a neighbouring Gaia star" if n_deb else "")
            + (f"; {n_glow} measure only the glow around an overloaded core (shows changes, not total brightness)"
               if n_glow else "")
            + (f"; error bars widened x{err_scale:.1f} to match the real scatter" if err_scale > 1.05 else "") + ".")
    out = {"name": slug, "label": man.get("name", slug), "ra": man["ra"], "dec": man["dec"],
           "source": "prebaked", "method": "aperture photometry r=2 px, sky ring 4-7 px; Gaia neighbours "
                                         "within 15\" fitted together", "note": note,
           "light_curve_band": lc_band, "variability": variability, "positions": positions, "points": points, "light_curve": light_curve}
    (web / "spectrum.json").write_text(json.dumps(out, indent=1))
    print(f"   -> {(web / 'spectrum.json').relative_to(REPO)}  ({note})")
    if light_curve:
        print("   light curve (" + lc_band + "): " + ", ".join(f"{p['date']} {p['flux_mjy']:.3g} mJy" for p in light_curve))
    plot(slug, out)
    return out


def plot(slug, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("   (pip install matplotlib to also get a picture of the spectrum)")
        return
    pts = out["points"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [2, 1]})
    for flagged, col, lab in ((False, "#2f6bff", "measurement"), (True, "#ffb020", "flagged")):
        s = [p for p in pts if p["flagged"] == flagged]
        if s:
            ax.errorbar([p["wavelength_um"] for p in s], [p["flux_mjy"] for p in s], [p["err_mjy"] for p in s],
                        fmt="o", ms=3, color=col, label=lab, alpha=0.85)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_xlabel("wavelength (µm)")
    ax.set_ylabel("brightness (mJy)")
    ax.set_title(f"{out['label']}: spectrum")
    ax.legend(fontsize=8)
    lc = out["light_curve"]
    if lc:
        bx.errorbar([p["date"] for p in lc], [p["flux_mjy"] for p in lc], [p["err_mjy"] for p in lc], fmt="o-",
                    color="#2f6bff")
        bx.set_title(f"light curve, {out['light_curve_band']}")
        bx.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    d = SCI_OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "spectrum.png", dpi=120)
    plt.close(fig)
    print(f"   plot -> {(d / 'spectrum.png').relative_to(REPO)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", action="append", help="target slug (repeatable)")
    p.add_argument("--all", action="store_true", help="every target with photos on this machine")
    p.add_argument("--rejudge", action="store_true",
                   help="only recompute the variability verdict of existing spectrum.json files (no photos needed)")
    a = p.parse_args()
    if a.rejudge:
        for f in sorted(WEB_DATA.glob("*/spectrum.json")):
            d = json.loads(f.read_text())
            if d.get("light_curve"):
                floor = (d.get("variability") or {}).get("systematic_floor", 0.05)
                d["variability"] = judge(d["light_curve"], floor, d.get("points"))
                f.write_text(json.dumps(d, indent=1))
                print(f"{f.parent.name}: {d['variability']['text']}")
        return
    slugs = a.target or []
    if a.all:
        slugs = [d.name for d in sorted(WEB_DATA.iterdir()) if (d / "exposures.json").exists() and d.name != "mock"]
    if not slugs:
        p.error("give --target <slug> or --all")
    for s in slugs:
        run(s, DEFAULT_MASK)


if __name__ == "__main__":
    main()
