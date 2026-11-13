#!/usr/bin/env python3
"""
Photometry quickstart (Alaa, Sprint 1): measure a star's brightness in real SPHEREx photos and read
the wavelength of each measurement. Then do the same for WISE 0855.

    pip install -r requirements.txt            # astropy, photutils, matplotlib ...
    python science/photometry_quickstart.py    # first run downloads 60 real photos (~250 MB) from NASA IRSA
    python science/photometry_quickstart.py --offline   # later runs reuse them

What it does, in order (each step prints what it found):
  1. Opens ONE SPHEREx file and lists its layers.
  2. Picks a medium-bright, isolated comparison star from the AllWISE catalogue near WISE 0855.
  3. In every photo: finds the star's pixel, adds up its light in a small circle (aperture),
     subtracts the sky measured in a ring around it, converts to milli-Jansky, and reads the wavelength
     at that pixel from the WCS-WAVE layer.
  4. Repeats step 3 for WISE 0855 at its predicted position on each date (it moves ~8"/yr).
  5. WISE 0855 has a Gaia star (G = 16.3) only ~8" away, inside the circle. So it also fits two star shapes at
     once (WISE 0855 + that star) to split the light between them ("deblending").
  6. Writes CSV tables + a spectrum plot to science/output/photometry_quickstart/.

Checks you can make:
  - The comparison star's SPHEREx brightness near 3.4 um and 4.6 um should be close to its WISE W1 / W2 values
    (printed and drawn as squares on the plot).
  - WISE 0855 should be ~zero below ~3.5 um and clearly positive at 4-5 um.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "science"))
OUT = REPO / "science" / "output" / "photometry_quickstart"

# WISE 0855 (same values as science/targets.json)
W0855 = dict(ra=133.795129, dec=-7.245147, epoch=2010.5, pmra=-8123.7, pmdec=673.2)
# The Gaia DR3 star ~8" from WISE 0855 in 2025-26 (from frontend/public/data/wise0855/catalogs.json)
NEIGHBOUR = dict(ra=133.758183, dec=-7.241156, epoch=2016.0, pmra=-6.19, pmdec=1.93)
# WISE zero points (Vega) to turn catalogue magnitudes into flux: band -> (wavelength um, zero-point Jy)
WISE_ZP = {"W1": (3.35, 309.54), "W2": (4.60, 171.79)}

AP_R = 2.0            # aperture radius in pixels (~12 arcsec); SPHEREx stars are ~2 px wide
ANN = (4.0, 7.0)      # sky ring inner/outer radius in pixels


def propagate(ra, dec, pmra, pmdec, from_year, to_year):
    dt = to_year - from_year
    return ra + pmra * dt / 3.6e6 / math.cos(math.radians(dec)), dec + pmdec * dt / 3.6e6


def mjd_to_year(mjd):
    return 2000.0 + (mjd - 51544.5) / 365.25


# ------------------------------------------------------------------ data
def get_photos(n, offline, cache_dir):
    """Returns the list of downloaded photos (dicts with 'file', 'mjd', 'detector')."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    index = cache_dir / "index.json"
    if offline:
        if not index.exists():
            sys.exit(f"--offline but nothing in {cache_dir}. Run once without --offline first.")
        return json.loads(index.read_text())["rows"]
    from fetch_cutouts import tap_query, download_all  # the team pipeline's own query + download code
    ra, dec = propagate(W0855["ra"], W0855["dec"], W0855["pmra"], W0855["pmdec"], W0855["epoch"], 2026.0)
    rows = tap_query(ra, dec, 0.12)  # every SPHEREx photo covering WISE 0855; 0.12 deg ~ 7' cutouts
    step = max(1, len(rows) // n)
    rows = rows[::step][:n]          # spread over all dates and all six detectors
    print(f"Downloading {len(rows)} of them (a spread across dates and detectors)...")
    rows = download_all(rows, cache_dir, workers=6)
    index.write_text(json.dumps({"rows": rows}, indent=1))
    return rows


def pick_comparison_star(ra0, dec0):
    """Medium-bright AllWISE star (W1 10.5-12.5) within 4', with no neighbour within 25" that is less than
    2 magnitudes fainter (fainter ones barely affect the measurement)."""
    cat = json.loads((REPO / "frontend/public/data/wise0855/catalogs.json").read_text())["allwise"]["rows"]
    def sep_arcsec(a, b, c, d):
        return 3600 * math.degrees(math.acos(min(1.0, math.sin(math.radians(b)) * math.sin(math.radians(d)) +
                                             math.cos(math.radians(b)) * math.cos(math.radians(d)) * math.cos(math.radians(a - c)))))
    best = None
    for ra, dec, w1, w2 in cat:
        if w1 is None or w2 is None or not (10.5 < w1 < 12.5):
            continue
        d0 = sep_arcsec(ra, dec, ra0, dec0)
        if d0 > 240 or d0 < 40:
            continue
        crowded = any(sep_arcsec(ra, dec, r2, d2) < 25 for r2, d2, w1b, _ in cat
                      if (r2, d2) != (ra, dec) and w1b is not None and w1b < w1 + 2.0)
        if not crowded and (best is None or d0 < best[0]):
            best = (d0, ra, dec, w1, w2)
    if best is None:
        sys.exit("No isolated comparison star found; widen the search in pick_comparison_star().")
    d0, ra, dec, w1, w2 = best
    return dict(ra=ra, dec=dec, w1=w1, w2=w2, dist_arcmin=d0 / 60)


# ------------------------------------------------------------------ measuring
def describe_file(path):
    from astropy.io import fits
    print(f"\nSTEP 1 - one SPHEREx file: {path.name}")
    meaning = {
        "IMAGE": "the picture: sky brightness per pixel, in MJy/sr",
        "FLAGS": "a number per pixel saying what is wrong with it (cosmic ray, hot pixel, ...)",
        "VARIANCE": "how uncertain each pixel is (noise squared)",
        "ZODI": "model of the glow from dust in our solar system; subtract it from IMAGE",
        "PSF": "how a star's blur looks (not needed today)",
        "EPSF": "how a star's blur looks (not needed today)",
        "WCS-WAVE": "lookup table: pixel -> wavelength (the colour that pixel saw)",
    }
    with fits.open(path) as h:
        for hdu in h[1:]:
            shape = hdu.data.shape if hdu.data is not None and hdu.name not in ("EPSF", "PSF", "WCS-WAVE") else ""
            print(f"   {hdu.name:9s} {str(shape):12s} {meaning.get(hdu.name, '')}")
        hdr = h["IMAGE"].header
        print(f"   detector: {hdr.get('DETECTOR', '?')}   date (MJD): {hdr.get('MJD-OBS', '?')}")


def measure(path, ra, dec):
    """Aperture photometry at (ra, dec) in one photo. Returns dict or None if off-image / bad pixels."""
    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning
    from astropy.wcs.utils import proj_plane_pixel_area
    from astropy import log as alog
    from photutils.aperture import CircularAperture, CircularAnnulus, ApertureStats, aperture_photometry
    import astropy.units as u

    warnings.simplefilter("ignore", FITSFixedWarning)
    alog.setLevel("WARNING")
    with fits.open(path) as h:
        img = h["IMAGE"].data.astype(float) - h["ZODI"].data.astype(float)
        var = h["VARIANCE"].data.astype(float)
        flags = h["FLAGS"].data
        hdr = h["IMAGE"].header
        wcs = WCS(hdr)
        x, y = wcs.world_to_pixel_values(ra, dec)
        ny, nx = img.shape
        if not (ANN[1] < x < nx - ANN[1] - 1 and ANN[1] < y < ny - ANN[1] - 1):
            return None
        # wavelength at this pixel from the WCS-WAVE lookup table (same recipe as the IRSA tutorial)
        sw = WCS(hdr, fobj=h, key="W")
        sw.sip = None
        wl, bw = sw.pixel_to_world(x, y)
        wl, bw = wl.to(u.um).value, bw.to(u.um).value
        mjd = float(hdr.get("MJD-OBS", np.nan))
        det = hdr.get("DETECTOR")

    ap = CircularAperture((x, y), r=AP_R)
    ann = CircularAnnulus((x, y), r_in=ANN[0], r_out=ANN[1])
    bad = ~np.isfinite(img) | ~np.isfinite(var)
    sky = ApertureStats(img, ann, mask=bad, sigma_clip=None).median          # sky level per pixel (MJy/sr)
    phot = aperture_photometry(img - sky, ap, error=np.sqrt(np.where(bad, 0, var)), mask=bad)
    # flagged = any pixel in the aperture carries a flag other than SOURCE (bit 21, "a known star is here")
    m = ap.to_mask(method="center").to_image(img.shape).astype(bool)
    flagged = bool(np.any((flags[m] & ~(1 << 21)) != 0))
    pix_sr = proj_plane_pixel_area(wcs) * (math.pi / 180) ** 2               # pixel area in steradians
    to_mjy = pix_sr * 1e9                                                    # MJy/sr * sr = MJy -> mJy
    return dict(wavelength_um=round(wl, 4), bandwidth_um=round(bw, 4), mjd=round(mjd, 4), detector=det,
                flux_mjy=float(phot["aperture_sum"][0]) * to_mjy, err_mjy=float(phot["aperture_sum_err"][0]) * to_mjy,
                flagged=flagged, x=round(float(x), 2), y=round(float(y), 2))


def _gauss(shape, x0, y0, sig):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * sig ** 2)) / (2 * np.pi * sig ** 2)  # sums to 1


def _fit(img, var, models):
    """Weighted linear least squares: img = sum(a_i * model_i) + sky. Returns amplitudes, errors, chi2."""
    ok = np.isfinite(img) & np.isfinite(var) & (var > 0)
    A = np.column_stack([m[ok] for m in models] + [np.ones(ok.sum())])
    w = 1 / np.sqrt(var[ok])
    coef, *_ = np.linalg.lstsq(A * w[:, None], img[ok] * w, rcond=None)
    cov = np.linalg.pinv((A * w[:, None]).T @ (A * w[:, None]))
    chi2 = float(((((A @ coef) - img[ok]) * w) ** 2).sum())
    return coef, np.sqrt(np.diag(cov)), chi2


def deblend(path, target, neighbour, star):
    """Fit WISE 0855 and its neighbour together. The blur width (sigma) is learned from the comparison star."""
    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning
    from astropy.wcs.utils import proj_plane_pixel_area
    import astropy.units as u
    from astropy import log as alog
    alog.setLevel("WARNING")
    warnings.simplefilter("ignore", FITSFixedWarning)
    with fits.open(path) as h:
        img = h["IMAGE"].data.astype(float) - h["ZODI"].data.astype(float)
        var = h["VARIANCE"].data.astype(float)
        hdr = h["IMAGE"].header
        wcs = WCS(hdr)
        sw = WCS(hdr, fobj=h, key="W")
        sw.sip = None
        xt, yt = (float(v) for v in wcs.world_to_pixel_values(*target))
        wl = sw.pixel_to_world(xt, yt)[0].to(u.um).value
        mjd = float(hdr.get("MJD-OBS", np.nan))
    R = 5
    def box(x, y):
        x, y = float(x), float(y)
        x0, y0 = int(round(x)), int(round(y))
        if not (R <= x0 < img.shape[1] - R and R <= y0 < img.shape[0] - R):
            return None
        return (slice(y0 - R, y0 + R + 1), slice(x0 - R, x0 + R + 1)), x - (x0 - R), y - (y0 - R)
    # 1) blur width from the comparison star (single source)
    bs = box(*wcs.world_to_pixel_values(star["ra"], star["dec"]))
    bt = box(xt, yt)
    if bs is None or bt is None:
        return None
    (sl, xs, ys) = bs
    best = None
    for sig in np.linspace(0.5, 1.8, 27):
        _, _, chi2 = _fit(img[sl], var[sl], [_gauss(img[sl].shape, xs, ys, sig)])
        if best is None or chi2 < best[1]:
            best = (sig, chi2)
    sig = best[0]
    # 2) two sources at known positions, same blur
    (sl, xa, ya) = bt
    xn, yn = (float(v) for v in wcs.world_to_pixel_values(*neighbour))
    xb, yb = xn - (xt - xa), yn - (yt - ya)
    coef, err, _ = _fit(img[sl], var[sl], [_gauss(img[sl].shape, xa, ya, sig), _gauss(img[sl].shape, xb, yb, sig)])
    to_mjy = proj_plane_pixel_area(wcs) * (math.pi / 180) ** 2 * 1e9
    return dict(wavelength_um=round(float(wl), 4), mjd=round(mjd, 4), sigma_px=round(float(sig), 2),
                flux_mjy=float(coef[0] * to_mjy), err_mjy=float(err[0] * to_mjy),
                neighbour_mjy=float(coef[1] * to_mjy), flagged=False)


def run_object(name, photos, cache_dir, ra, dec, pm=None):
    rows = []
    for p in photos:
        r_ra, r_dec = ra, dec
        if pm:
            r_ra, r_dec = propagate(ra, dec, pm[0], pm[1], pm[2], mjd_to_year(p["mjd"]))
        m = measure(cache_dir / p["file"], r_ra, r_dec)
        if m:
            rows.append(m)
    rows.sort(key=lambda r: r["wavelength_um"])
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{name}.csv"
    with f.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"   {len(rows)} measurements -> {f.relative_to(REPO)}")
    return rows


def band_mean(rows, lo, hi):
    sel = [r for r in rows if lo <= r["wavelength_um"] <= hi and not r["flagged"]]
    if not sel:
        return None, 0
    w = np.array([1 / max(r["err_mjy"], 1e-6) ** 2 for r in sel])
    f = np.array([r["flux_mjy"] for r in sel])
    return float((w * f).sum() / w.sum()), len(sel)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=60, help="how many photos to download (default 60)")
    ap.add_argument("--offline", action="store_true", help="reuse photos downloaded earlier")
    ap.add_argument("--cache-dir", default=str(REPO / "science" / "cache" / "photometry_quickstart"))
    a = ap.parse_args()
    cache_dir = Path(a.cache_dir)

    photos = get_photos(a.n, a.offline, cache_dir)
    print(f"{len(photos)} photos available")
    describe_file(cache_dir / photos[0]["file"])

    now_ra, now_dec = propagate(W0855["ra"], W0855["dec"], W0855["pmra"], W0855["pmdec"], W0855["epoch"], 2025.9)
    star = pick_comparison_star(now_ra, now_dec)
    print(f"\nSTEP 2 - comparison star: RA {star['ra']:.5f}  Dec {star['dec']:+.5f}, {star['dist_arcmin']:.1f}' from WISE 0855,"
          f" WISE W1 = {star['w1']} mag, W2 = {star['w2']} mag")

    print("\nSTEP 3 - measuring the comparison star in every photo")
    srows = run_object("comparison_star", photos, cache_dir, star["ra"], star["dec"])
    print("\nSTEP 4 - measuring WISE 0855 at its predicted position on each date")
    wrows = run_object("wise0855", photos, cache_dir, W0855["ra"], W0855["dec"],
                       pm=(W0855["pmra"], W0855["pmdec"], W0855["epoch"]))

    print("\nSTEP 5 - WISE 0855 deblended from its neighbour star (two-star fit)")
    drows = []
    for p in photos:
        yr = mjd_to_year(p["mjd"])
        tgt = propagate(W0855["ra"], W0855["dec"], W0855["pmra"], W0855["pmdec"], W0855["epoch"], yr)
        nb = propagate(NEIGHBOUR["ra"], NEIGHBOUR["dec"], NEIGHBOUR["pmra"], NEIGHBOUR["pmdec"], NEIGHBOUR["epoch"], yr)
        try:
            d = deblend(cache_dir / p["file"], tgt, nb, star)
        except Exception as e:  # a photo with too many bad pixels near the target
            print(f"   skipped {p['file']}: {e!r}")
            d = None
        if d:
            drows.append(d)
    drows.sort(key=lambda r: r["wavelength_um"])
    with (OUT / "wise0855_deblended.csv").open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(drows[0].keys()))
        wr.writeheader()
        wr.writerows(drows)
    print(f"   {len(drows)} measurements -> {(OUT / 'wise0855_deblended.csv').relative_to(REPO)}")

    print("\nCHECKS")
    for band, (wl, zp) in WISE_ZP.items():
        mag = star["w1"] if band == "W1" else star["w2"]
        wise_mjy = zp * 10 ** (-mag / 2.5) * 1000
        sx, n = band_mean(srows, wl - 0.25, wl + 0.25)
        txt = f"{sx:.2f} mJy from {n} photos" if sx is not None else "no SPHEREx photo at this wavelength"
        print(f"   comparison star near {wl} um: WISE says {wise_mjy:.2f} mJy, SPHEREx gives {txt}")
    short, ns = band_mean(wrows, 0.7, 3.0)
    long_, nl = band_mean(wrows, 4.0, 5.1)
    print(f"   WISE 0855 at 0.7-3.0 um: {short if short is None else round(short, 3)} mJy ({ns} photos)  <- should be ~0")
    print(f"   WISE 0855 at 4.0-5.1 um: {long_ if long_ is None else round(long_, 3)} mJy ({nl} photos)  <- should be clearly > 0")
    print("   (simple circle: the neighbour star leaks in. Deblended values:)")
    dshort, n1 = band_mean(drows, 0.7, 3.0)
    dlong, n2 = band_mean(drows, 4.0, 5.1)
    w2 = 171.79 * 10 ** (-14.02 / 2.5) * 1000  # WISE 0855 W2 = 14.02 (Wright et al. 2014)
    print(f"   WISE 0855 deblended 0.7-3.0 um: {dshort:.3f} mJy ({n1} photos)  <- should be ~0")
    print(f"   WISE 0855 deblended 4.0-5.1 um: {dlong:.3f} mJy ({n2} photos); WISE W2 says ~{w2:.2f} mJy at 4.6 um")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.5))
    ok = [r for r in srows if not r["flagged"]]
    ax.errorbar([r["wavelength_um"] for r in ok], [r["flux_mjy"] for r in ok], [r["err_mjy"] for r in ok],
                fmt="o", ms=3, color="#2f6bff", label="SPHEREx, one point per photo")
    for band, (wl, zp) in WISE_ZP.items():
        mag = star["w1"] if band == "W1" else star["w2"]
        ax.plot(wl, zp * 10 ** (-mag / 2.5) * 1000, "s", color="#2f6bff", mfc="none", ms=11)
    ax.plot([], [], "s", color="#2f6bff", mfc="none", label="WISE catalogue (W1, W2)")
    ax.set_title("Comparison star: calibration check")
    for rows, label, col in ((wrows, "simple circle (neighbour star leaks in)", "#f2a08f"),
                             (drows, "deblended from the neighbour", "#e8341c")):
        ok = [r for r in rows if not r["flagged"]]
        bx.errorbar([r["wavelength_um"] for r in ok], [r["flux_mjy"] for r in ok], [r["err_mjy"] for r in ok],
                    fmt="o", ms=3, color=col, label=label, alpha=0.9)
    bx.plot(4.6, 171.79 * 10 ** (-14.02 / 2.5) * 1000, "s", color="#e8341c", mfc="none", ms=11, label="WISE W2 catalogue")
    bx.set_title("WISE 0855: dark until ~4 µm, then glows")
    for a_ in (ax, bx):
        a_.axhline(0, color="#999", lw=0.8)
        a_.set_xlabel("wavelength (µm)")
        a_.set_ylabel("brightness (mJy)")
        a_.legend(fontsize=8)
    fig.suptitle("SPHEREx single-photo spectra near WISE 0855", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "spectra.png", dpi=130)
    print(f"\nPlot -> {(OUT / 'spectra.png').relative_to(REPO)}")


if __name__ == "__main__":
    main()
