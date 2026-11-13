#!/usr/bin/env python3
"""
Fetch SPHEREx cutouts for one sky position and bake them into video frames.

    python science/fetch_cutouts.py --target wise0855            # from science/targets.json
    python science/fetch_cutouts.py --all                        # all five test targets
    python science/fetch_cutouts.py --ra 133.795 --dec -7.245 --slug mypatch --size 0.5
    python science/fetch_cutouts.py --target wise0855 --offline  # reprocess cached FITS, no network

Pipeline (details in README.md):
  1. Resolve the position (SIMBAD + proper motion when available).
  2. IRSA TAP query on spherex.artifact JOIN spherex.plane: every Spectral Image
     covering the position (QR3 + DR1 at the time of writing), with a cutout URL.
  3. Download the cutouts (IMAGE, FLAGS, VARIANCE, ZODI, PSF, WCS-WAVE) to a local cache.
  4. IMAGE - ZODI; mask bad pixels by flag *name* (read from the FLAGS header).
  5. Reproject every cutout onto one north-up TAN grid centred on the target.
  6. Split exposures into survey passes ("epochs") by time gaps; inverse-variance
     stack per (epoch, detector) and per epoch over all detectors (detector 0).
  7. Difference frame = epoch stack - stack of all *other* epochs.
  8. Write PNGs + manifest.json (API contract shape) + exposures.json + stacks.fits.

Outputs:
  frontend/public/data/<slug>/   PNG frames, manifest.json, exposures.json  (served to the browser)
  science/output/<slug>/         stacks.fits (float data for photometry / detection work)
  science/cache/<slug>/          raw cutout FITS + query index (git-ignored)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
TARGETS_FILE = REPO / "science" / "targets.json"
WEB_DATA = REPO / "frontend" / "public" / "data"
SCI_OUT = REPO / "science" / "output"
CACHE = REPO / "science" / "cache"

PIXEL_SCALE_DEG = 6.15 / 3600.0  # SPHEREx native pixel (~6.15-6.2 arcsec)
IRSA = "https://irsa.ipac.caltech.edu/"

# Flags masked before stacking, matched by name against the MSKNnnnn cards in the FLAGS header.
# OVERFLOW / NONLINEAR / SOURCE / BLOOM / HALO are deliberately NOT masked: they sit on bright stars
# (Barnard's Star) and SOURCE marks every catalogued star. They are still counted in the flag summary.
DEFAULT_MASK = ["TRANSIENT", "SUR_ERROR", "PHANTOM", "NONFUNC", "DICHROIC", "MISSING_DATA",
                "HOT", "COLD", "PHANMISS", "PERSIST", "OUTLIER",
                # artifacts that would otherwise appear as fake "movers" in difference images
                "STREAK", "SNOWBALL", "GHOST", "GHOST_FPA", "GHOST_EXT", "CROSSTALK"]
# Fallback bit numbers if a header has no MSKN cards (from IRSA's Spectrophotometry Tool docs).
FALLBACK_BITS = {"TRANSIENT": 0, "OVERFLOW": 1, "SUR_ERROR": 2, "PHANTOM": 4, "REFERENCE": 5,
                 "NONFUNC": 6, "DICHROIC": 7, "MISSING_DATA": 9, "HOT": 10, "COLD": 11,
                 "FULLSAMPLE": 12, "PHANMISS": 14, "NONLINEAR": 15, "VAR_UNDER": 16,
                 "PERSIST": 17, "PERSIST_UNK": 18, "OUTLIER": 19, "SOURCE": 21}
# Flags reported in the per-frame summary (the "contamination flags" the challenge asks for).
SUMMARY_FLAGS = ["TRANSIENT", "OVERFLOW", "NONLINEAR", "PERSIST", "HOT", "COLD",
                 "MISSING_DATA", "OUTLIER", "NONFUNC", "STREAK", "GHOST", "SNOWBALL", "CROSSTALK", "BLOOM"]


try:  # silence astropy's repeated SIP notice from the WCS-WAVE lookup (SIP is disabled there on purpose)
    from astropy import log as _alog
    _alog.setLevel("WARNING")
except Exception:
    pass


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- position

def load_targets():
    return {t["slug"]: t for t in json.loads(TARGETS_FILE.read_text())["targets"]}


def resolve_position(name, ra, dec, epoch_year, offline, pm=(0.0, 0.0), coord_epoch=2000.0, use_simbad=True):
    """Return (ra, dec, pmra, pmdec, note, (ra2000, dec2000)); ra/dec propagated to epoch_year.

    Without SIMBAD the given ra/dec are taken to be at coord_epoch with proper motion pm (mas/yr)."""
    pmra, pmdec = pm
    note = f"catalogue position (epoch {coord_epoch}) + proper motion" if any(pm) else "given coordinates"
    if coord_epoch != 2000.0:
        ra, dec = propagate(ra, dec, pmra, pmdec, 2000.0 - (coord_epoch - 2000.0))
    if name and use_simbad and not offline:
        try:
            from astroquery.simbad import Simbad
            s = Simbad()
            s.add_votable_fields("pmra", "pmdec")
            r = s.query_object(name)
            if r is not None and len(r):
                cols = {c.lower(): c for c in r.colnames}
                ra0, dec0 = float(r[cols["ra"]][0]), float(r[cols["dec"]][0])
                pmra = float(r[cols["pmra"]][0]) if "pmra" in cols and not np.ma.is_masked(r[cols["pmra"]][0]) else 0.0
                pmdec = float(r[cols["pmdec"]][0]) if "pmdec" in cols and not np.ma.is_masked(r[cols["pmdec"]][0]) else 0.0
                ra, dec = ra0, dec0
                note = f"SIMBAD '{name}' (J2000) + proper motion"
        except Exception as e:  # network / parsing: fall back to targets.json values
            log(f"  SIMBAD lookup failed ({e!r}); using fallback coordinates")
    ra_e, dec_e = propagate(ra, dec, pmra, pmdec, epoch_year)
    return ra_e, dec_e, pmra, pmdec, note, (ra, dec)


def propagate(ra2000, dec2000, pmra, pmdec, year):
    """Linear proper-motion propagation from J2000 (fine for a few arcmin)."""
    dtyr = year - 2000.0
    dec = dec2000 + pmdec * dtyr / 3.6e6
    ra = ra2000 + pmra * dtyr / 3.6e6 / max(math.cos(math.radians(dec2000)), 1e-6)
    return ra % 360.0, dec


def mjd_to_year(mjd):
    return 2000.0 + (mjd - 51544.5) / 365.25


def mjd_to_date(mjd):
    return (dt.datetime(1858, 11, 17) + dt.timedelta(days=float(mjd))).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- query

def tap_query(ra, dec, size):
    from astroquery.ipac.irsa import Irsa
    q = f"""
SELECT
    'https://irsa.ipac.caltech.edu/' || a.uri || '?center={ra},{dec}d&size={size}' AS cutout_url,
    a.uri AS raw_uri,
    p.time_bounds_lower AS mjd,
    p.energy_bandpassname AS bandpass
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE 1 = CONTAINS(POINT('ICRS', {ra}, {dec}), p.poly)
ORDER BY p.time_bounds_lower
"""
    t0 = time.time()
    tab = Irsa.query_tap(q).to_table()
    log(f"  TAP: {len(tab)} spectral images in {time.time() - t0:.1f}s")
    rows = []
    for r in tab:
        bp = str(r["bandpass"])
        det = int("".join(ch for ch in bp.split("-")[-1] if ch.isdigit()) or 0)
        rows.append({"url": str(r["cutout_url"]), "raw_uri": str(r["raw_uri"]),
                     "mjd": float(r["mjd"]), "detector": det, "bandpass": bp})
    return dedupe(rows)


def dedupe(rows):
    """The same exposure can appear in more than one release (e.g. QR3 and DR1); keep one, prefer DR."""
    best = {}
    for r in rows:
        key = (round(r["mjd"] * 86400), r["detector"])
        prev = best.get(key)
        if prev is None or ("/dr" in r["raw_uri"].lower() and "/dr" not in prev["raw_uri"].lower()):
            best[key] = r
    out = sorted(best.values(), key=lambda r: (r["mjd"], r["detector"]))
    if len(out) != len(rows):
        log(f"  dropped {len(rows) - len(out)} duplicate exposures across releases")
    return out


# --------------------------------------------------------------------------- download

def download_all(rows, cache_dir, workers):
    import requests
    cache_dir.mkdir(parents=True, exist_ok=True)

    def one(r):
        fn = cache_dir / (hashlib.sha1(r["url"].encode()).hexdigest()[:16] + ".fits")
        r["file"] = fn.name
        if fn.exists() and fn.stat().st_size > 0:
            return r, None
        for attempt in range(4):
            try:
                resp = requests.get(r["url"], timeout=120)
                resp.raise_for_status()
                tmp = fn.with_suffix(".part")
                tmp.write_bytes(resp.content)
                tmp.rename(fn)
                return r, None
            except Exception as e:  # transient IRSA errors are common; back off and retry
                err = e
                time.sleep(2 * (attempt + 1))
        return r, err

    ok, failed = [], 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (r, err) in enumerate(ex.map(one, rows), 1):
            if err:
                failed += 1
                log(f"  ! failed {r['url'][:90]}... ({err})")
            else:
                ok.append(r)
            if i % 20 == 0 or i == len(rows):
                log(f"  downloaded {i}/{len(rows)}")
    if failed:
        log(f"  {failed} cutouts failed; continuing with {len(ok)}")
    return ok


# --------------------------------------------------------------------------- per-exposure processing

def flag_bits(header):
    bits = {}
    for key in header:
        if key.startswith("MSKN"):
            try:
                bits[str(header[key]).strip().upper()] = int(key[4:])
            except ValueError:
                pass
    return bits or dict(FALLBACK_BITS)


def process_exposure(path, ra, dec, target_grid_wcs, shape, mask_names):
    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    warnings.simplefilter("ignore", FITSFixedWarning)
    with fits.open(path, memmap=False) as hdul:
        names = [h.name for h in hdul]
        img_hdu = hdul["IMAGE"] if "IMAGE" in names else hdul[1]
        hdr = img_hdu.header
        image = img_hdu.data.astype(np.float64)
        zodi = hdul["ZODI"].data.astype(np.float64) if "ZODI" in names else 0.0
        var = hdul["VARIANCE"].data.astype(np.float64) if "VARIANCE" in names else np.ones_like(image)
        flags = hdul["FLAGS"].data.astype(np.int64) if "FLAGS" in names else np.zeros(image.shape, np.int64)
        bits = flag_bits(hdul["FLAGS"].header) if "FLAGS" in names else dict(FALLBACK_BITS)

        wcs = WCS(hdr)
        coord = SkyCoord(ra * u.deg, dec * u.deg)
        x, y = wcs.world_to_pixel(coord)

        wl = bw = None
        try:  # wavelength at the target pixel from the WCS-WAVE lookup table
            swcs = WCS(hdr, fobj=hdul, key="W")
            swcs.sip = None
            w, b = swcs.pixel_to_world(x, y)
            wl, bw = float(w.to(u.um).value), float(b.to(u.um).value)
        except Exception:
            pass
        version = hdul[0].header.get("VERSION", "")

    bad_mask = 0
    for n in mask_names:
        if n in bits:
            bad_mask |= 1 << bits[n]
    sci = image - zodi
    bad = ((flags & bad_mask) != 0) | ~np.isfinite(sci) | ~np.isfinite(var) | (var <= 0)
    sci[bad] = np.nan
    var[bad] = np.nan
    # remove what ZODI leaves behind: a sigma-clipped median sky level per exposure, so passes difference cleanly
    good = sci[np.isfinite(sci)]
    sky = 0.0
    if good.size > 50:
        from astropy.stats import sigma_clipped_stats
        _, sky, _ = sigma_clipped_stats(good, sigma=3.0, maxiters=5)
        sci = sci - sky

    summary = {n: int(np.count_nonzero(flags & (1 << bits[n]))) for n in SUMMARY_FLAGS if n in bits}

    try:
        from reproject import reproject_interp
        sci_r, _ = reproject_interp((sci, wcs), target_grid_wcs, shape_out=shape, order="bilinear")
        var_r, _ = reproject_interp((var, wcs), target_grid_wcs, shape_out=shape, order="bilinear")
    except ImportError:  # fallback: no reprojection, centre-crop/pad (rough alignment only)
        sci_r, var_r = center_crop(sci, x, y, shape), center_crop(var, x, y, shape)

    return {"sci": sci_r.astype(np.float32), "var": var_r.astype(np.float32),
            "x_cut": float(x), "y_cut": float(y), "wavelength_um": wl, "bandwidth_um": bw,
            "flags": summary, "n_masked": int(bad.sum()), "version": version, "sky_mjysr": float(sky)}


def center_crop(a, x, y, shape):
    out = np.full(shape, np.nan)
    h, w = shape
    x0, y0 = int(round(x)) - w // 2, int(round(y)) - h // 2
    for j in range(h):
        for i in range(w):
            yy, xx = y0 + j, x0 + i
            if 0 <= yy < a.shape[0] and 0 <= xx < a.shape[1]:
                out[j, i] = a[yy, xx]
    return out


def make_grid(ra, dec, size_deg):
    from astropy.wcs import WCS
    n = int(math.ceil(size_deg / PIXEL_SCALE_DEG))
    n += (n + 1) % 2  # odd so the target sits on the centre pixel
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-PIXEL_SCALE_DEG, PIXEL_SCALE_DEG]
    return w, (n, n)


# --------------------------------------------------------------------------- stacking

def weighted_stack(scis, vars_):
    s = np.stack(scis).astype(np.float64)
    v = np.stack(vars_).astype(np.float64)
    w = np.where(np.isfinite(s) & np.isfinite(v) & (v > 0), 1.0 / v, 0.0)
    s = np.where(w > 0, s, 0.0)
    wsum = w.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(wsum > 0, (w * s).sum(0) / wsum, np.nan)
        var = np.where(wsum > 0, 1.0 / wsum, np.nan)
    return mean.astype(np.float32), var.astype(np.float32)


def split_epochs(mjds, gap_days, max_span_days=90.0, chunk_days=60.0):
    """Group photos into survey passes: a new pass starts after a gap > gap_days.
    Near the ecliptic poles SPHEREx looks almost continuously, so gaps may never come;
    any pass longer than max_span_days is then cut into chunk_days pieces."""
    order = np.argsort(mjds)
    labels = np.zeros(len(mjds), int)
    e = 0
    for k in range(1, len(order)):
        if mjds[order[k]] - mjds[order[k - 1]] > gap_days:
            e += 1
        labels[order[k]] = e
    out = np.zeros(len(mjds), int)
    nxt = 0
    for g in range(labels.max() + 1):
        sel = labels == g
        t0, t1 = mjds[sel].min(), mjds[sel].max()
        if t1 - t0 > max_span_days:
            n = int(math.ceil((t1 - t0) / chunk_days))
            sub = np.minimum(((mjds[sel] - t0) / ((t1 - t0) / n)).astype(int), n - 1)
            used = np.unique(sub)
            remap = {u: i for i, u in enumerate(used)}
            out[sel] = nxt + np.array([remap[v] for v in sub])
            nxt += len(used)
        else:
            out[sel] = nxt
            nxt += 1
    return out


# --------------------------------------------------------------------------- PNG output

def robust_sigma(a):
    a = a[np.isfinite(a)]
    if a.size == 0:
        return 1.0
    return float(1.4826 * np.median(np.abs(a - np.median(a)))) or float(np.std(a)) or 1.0


def stretch_limits(ref):
    f = ref[np.isfinite(ref)]
    if f.size == 0:
        return 0.0, 1.0
    med, sig = float(np.median(f)), robust_sigma(f)
    lo = med - 2 * sig
    hi = max(float(np.percentile(f, 99.7)), med + 10 * sig)
    return lo, hi


def saturated_cores(nan, t, bright=0.6):
    """Holes (connected blank pixels) whose 2-pixel rim is mostly bright (stretched value > `bright`)."""
    from scipy import ndimage
    out = np.zeros_like(nan)
    lab, n = ndimage.label(nan)
    for k in range(1, n + 1):
        blob = lab == k
        if blob.sum() > 400:  # a big blank area is an edge of the field, not a star
            continue
        rim = ndimage.binary_dilation(blob, iterations=2) & ~nan
        if rim.any() and np.median(t[rim]) > bright:
            out |= blob
    return out


def to_png(a, path, lo, hi, mode="asinh"):
    from PIL import Image
    a = np.array(a, dtype=np.float64)
    nan = ~np.isfinite(a)
    if mode == "diff":  # symmetric: mid-grey = no change, white = brighter now, black = fainter now
        t = np.clip((a - lo) / (hi - lo), 0, 1)
    else:
        t = np.clip((a - lo) / (hi - lo), 0, 1)
        k = 10.0
        t = np.arcsinh(k * t) / np.arcsinh(k)
    t[nan] = 0.0
    if mode != "diff":
        # A blank hole whose edge is bright is the core of a star too bright to measure (the camera
        # overloaded; NASA's file has no valid value there). Show it white, like any overexposed photo,
        # instead of as missing data. True gaps (dark or no surroundings) stay transparent.
        sat = saturated_cores(nan, t)
        t[sat] = 1.0
        nan = nan & ~sat
    g = (t * 255).round().astype(np.uint8)
    alpha = np.where(nan, 0, 255).astype(np.uint8)  # transparent = no data (so it can't read as "fainter")
    # flip vertically: FITS row 0 is the bottom (south), PNG row 0 is the top -> north up, east left
    Image.fromarray(np.dstack([g, alpha])[::-1].copy()).save(path, optimize=True)  # 2 channels -> PNG "LA"


# --------------------------------------------------------------------------- main bake

def bake(job, args):
    slug, name, ra_in, dec_in, size = job["slug"], job["name"], job["ra"], job["dec"], job["size"]
    log(f"\n== {slug} ==")
    cache_dir = CACHE / slug
    web_dir = WEB_DATA / slug
    sci_dir = SCI_OUT / slug
    for d in (cache_dir, web_dir, sci_dir):
        d.mkdir(parents=True, exist_ok=True)
    index_file = cache_dir / "index.json"

    ra, dec, pmra, pmdec, pos_note, (ra2000, dec2000) = resolve_position(
        name, ra_in, dec_in, args.epoch, args.offline, job["pm"], job["coord_epoch"], job["use_simbad"])
    log(f"  centre {ra:.6f} {dec:+.6f} at J{args.epoch} ({pos_note}); pm = {pmra:.0f}, {pmdec:.0f} mas/yr")

    if args.offline:
        if not index_file.exists():
            sys.exit(f"  --offline but no {index_file}")
        idx = json.loads(index_file.read_text())
        rows = idx["rows"]
    else:
        # SPHEREx frames are rotated relative to north-up; ask for ~1.45x so the square grid has no empty corners
        rows = tap_query(ra, dec, round(size * 1.45, 4))
        if args.max_exposures and len(rows) > args.max_exposures:
            # an even spread over all dates and detectors, not just the first N
            keep = np.unique(np.linspace(0, len(rows) - 1, args.max_exposures).round().astype(int))
            rows = [rows[i] for i in keep]
            log(f"  keeping {len(rows)} photos spread evenly over the dates (--max-exposures)")
        rows = download_all(rows, cache_dir, args.workers)
        index_file.write_text(json.dumps({"ra": ra, "dec": dec, "size": size,
                                          "queried": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                          "rows": rows}, indent=1))
    if not rows:
        log("  no exposures found")
        return None

    grid, shape = make_grid(ra, dec, size)
    mask_names = [m.strip().upper() for m in args.mask.split(",") if m.strip()]

    exps = []
    for i, r in enumerate(rows, 1):
        try:
            res = process_exposure(cache_dir / r["file"], ra, dec, grid, shape, mask_names)
        except Exception as e:
            log(f"  ! could not process {r['file']}: {e!r}")
            continue
        res.update(r)
        exps.append(res)
        if i % 25 == 0 or i == len(rows):
            log(f"  processed {i}/{len(rows)}")
    if not exps:
        log("  nothing processed")
        return None

    mjds = np.array([e["mjd"] for e in exps])
    epochs = split_epochs(mjds, args.gap_days)
    for e, ep in zip(exps, epochs):
        e["epoch"] = int(ep)
    n_ep = int(epochs.max()) + 1
    dets = sorted({e["detector"] for e in exps})
    log(f"  {len(exps)} exposures, {n_ep} epochs, detectors {dets}")

    # stacks[(epoch, det)] ; det 0 = all detectors combined
    groups = {}
    for e in exps:
        groups.setdefault((e["epoch"], e["detector"]), []).append(e)
        groups.setdefault((e["epoch"], 0), []).append(e)
    stacks = {k: weighted_stack([g["sci"] for g in v], [g["var"] for g in v]) for k, v in groups.items()}
    deep = {}
    for d in [0] + dets:
        members = [e for e in exps if d == 0 or e["detector"] == d]
        deep[d] = weighted_stack([m["sci"] for m in members], [m["var"] for m in members])

    from astropy.io import fits
    hdus = [fits.PrimaryHDU(header=grid.to_header())]
    hdus[0].header["TARGET"] = slug
    hdus[0].header["RA_EP"] = (ra, f"target RA at J{args.epoch}")
    hdus[0].header["DEC_EP"] = (dec, f"target Dec at J{args.epoch}")

    visits, deep_entries, det_info = [], [], {}
    for stale in web_dir.glob("*.png"):  # frames from an earlier run would otherwise linger in git
        stale.unlink()
    for d in [0] + dets:
        wls = [e["wavelength_um"] for e in exps if (d == 0 or e["detector"] == d) and e["wavelength_um"]]
        det_info[d] = [round(min(wls), 3), round(max(wls), 3)] if wls else None

    for d in [0] + dets:
        lo, hi = stretch_limits(deep[d][0])
        tag = "all" if d == 0 else f"d{d}"
        fn = f"deep_{tag}.png"
        to_png(deep[d][0], web_dir / fn, lo, hi)
        n_members = sum(1 for e in exps if d == 0 or e["detector"] == d)
        deep_entries.append({"detector": d, "image_url": f"/data/{slug}/{fn}",
                             "n_exposures": n_members, "wavelength_um": det_info[d]})
        h = fits.ImageHDU(deep[d][0], header=grid.to_header(), name=f"DEEP_{tag.upper()}")
        hdus.append(h)

        for ep in range(n_ep):
            if (ep, d) not in stacks:
                continue
            members = groups[(ep, d)]
            img, var = stacks[(ep, d)]
            others = [e for e in exps if e["epoch"] != ep and (d == 0 or e["detector"] == d)]
            mid = float(np.median([m["mjd"] for m in members]))
            date = mjd_to_date(mid)
            base = f"{date}_{tag}"
            to_png(img, web_dir / f"{base}.png", lo, hi)
            diff_url, diff_sigma = None, None
            if others:
                ref, ref_var = weighted_stack([o["sci"] for o in others], [o["var"] for o in others])
                diff = img - ref
                sig = robust_sigma(diff)
                to_png(diff, web_dir / f"{base}_diff.png", -5 * sig, 5 * sig, mode="diff")
                diff_url, diff_sigma = f"/data/{slug}/{base}_diff.png", sig
                hdus.append(fits.ImageHDU(diff.astype(np.float32), header=grid.to_header(),
                                          name=f"DIFF_E{ep}_{tag.upper()}"))
            hdus.append(fits.ImageHDU(img, header=grid.to_header(), name=f"IMG_E{ep}_{tag.upper()}"))
            hdus.append(fits.ImageHDU(var, header=grid.to_header(), name=f"VAR_E{ep}_{tag.upper()}"))

            pra, pdec = propagate(ra2000, dec2000, pmra, pmdec, mjd_to_year(mid))
            px, py = grid.world_to_pixel_values(pra, pdec)
            flags = {}
            for m in members:
                for k, v in m["flags"].items():
                    flags[k] = flags.get(k, 0) + v
            wls = [m["wavelength_um"] for m in members if m["wavelength_um"]]
            visits.append({
                "date": date, "mjd": round(mid, 5), "epoch": ep, "detector": d,
                "wavelength_um": [round(min(wls), 3), round(max(wls), 3)] if wls else None,
                "image_url": f"/data/{slug}/{base}.png", "diff_url": diff_url,
                "diff_sigma_mjysr": diff_sigma, "n_exposures": len(members), "flags": flags,
                # predicted target position on this date, as a fraction of the image (0,0 = top-left)
                "predicted": {"ra": round(pra, 6), "dec": round(pdec, 6),
                              "fx": round(float(px + 0.5) / shape[1], 4),
                              "fy": round(1 - float(py + 0.5) / shape[0], 4)},
            })

    fits.HDUList(hdus).writeto(sci_dir / "stacks.fits", overwrite=True)

    manifest = {
        "target": slug, "name": job.get("label") or name or slug, "ra": round(ra, 6), "dec": round(dec, 6),
        "ra_j2000": ra2000, "dec_j2000": dec2000, "pm_mas_yr": [pmra, pmdec],
        "position_note": pos_note, "fov": size, "pixels": shape[0],
        "pixel_scale_arcsec": PIXEL_SCALE_DEG * 3600, "orientation": "north up, east left",
        "n_exposures": len(exps), "n_epochs": n_ep, "detectors": dets,
        "detector_wavelength_um": {str(k): v for k, v in det_info.items()},
        "masked_flags": mask_names, "source": "prebaked",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "visits": sorted(visits, key=lambda v: (v["detector"], v["mjd"])),
        "deep": deep_entries,
    }
    (web_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    exp_rows = [{k: e.get(k) for k in ("mjd", "epoch", "detector", "bandpass", "wavelength_um",
                                       "bandwidth_um", "x_cut", "y_cut", "file", "url", "flags",
                                       "n_masked", "version", "sky_mjysr")} for e in exps]
    for r in exp_rows:
        r["date"] = mjd_to_date(r["mjd"])
    (web_dir / "exposures.json").write_text(json.dumps(exp_rows, indent=1))
    log(f"  wrote {len(visits)} frames -> {web_dir.relative_to(REPO)}  and  {sci_dir.relative_to(REPO)}/stacks.fits")
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", help="slug from science/targets.json")
    g.add_argument("--all", action="store_true", help="all targets in science/targets.json")
    g.add_argument("--ra", type=float, help="RA in degrees (with --dec and --slug)")
    p.add_argument("--dec", type=float)
    p.add_argument("--slug", help="output folder name for --ra/--dec")
    p.add_argument("--name", help="SIMBAD name to resolve (overrides --ra/--dec when online)")
    p.add_argument("--size", type=float, help="field of view in degrees (default from targets.json, 0.5)")
    p.add_argument("--epoch", type=float, default=2026.0, help="epoch for the cutout centre (decimal year)")
    p.add_argument("--pmra", type=float, default=0.0, help="proper motion in RA*cos(Dec), mas/yr (no SIMBAD)")
    p.add_argument("--pmdec", type=float, default=0.0, help="proper motion in Dec, mas/yr (no SIMBAD)")
    p.add_argument("--coord-epoch", type=float, default=2000.0, help="epoch of --ra/--dec (decimal year)")
    p.add_argument("--gap-days", type=float, default=60.0,
                   help="photos closer than this (days) form one survey pass; SPHEREx revisits a spot ~every 6 months")
    p.add_argument("--mask", default=",".join(DEFAULT_MASK), help="comma-separated flag names to mask")
    p.add_argument("--workers", type=int, default=6, help="parallel downloads")
    p.add_argument("--max-exposures", type=int, default=0,
                   help="download at most N photos, spread evenly over all dates (0 = all)")
    p.add_argument("--offline", action="store_true", help="reuse science/cache/<slug>; no network")
    p.add_argument("--no-catalogs", action="store_true", help="skip the Gaia/AllWISE overlay download")
    args = p.parse_args()

    targets = load_targets()
    def from_target(t):
        # The five test targets carry their own proper motion (targets.json), so SIMBAD is not needed.
        return {"slug": t["slug"], "name": t["simbad"], "label": t["label"], "ra": t["ra"], "dec": t["dec"],
                "size": args.size or t["fov"], "pm": (t.get("pmra", 0.0), t.get("pmdec", 0.0)),
                "coord_epoch": t.get("coord_epoch", 2000.0), "use_simbad": "pmra" not in t}

    if args.all:
        jobs = [from_target(t) for t in targets.values()]
    elif args.target:
        if args.target not in targets:
            sys.exit(f"unknown target {args.target}; choose from {', '.join(targets)}")
        jobs = [from_target(targets[args.target])]
    else:
        if args.dec is None or not args.slug:
            sys.exit("--ra needs --dec and --slug")
        jobs = [{"slug": args.slug, "name": args.name, "label": args.name, "ra": args.ra, "dec": args.dec,
                 "size": args.size or 0.5, "pm": (args.pmra, args.pmdec), "coord_epoch": args.coord_epoch,
                 "use_simbad": bool(args.name) and not (args.pmra or args.pmdec)}]

    done = []
    for job in jobs:
        try:
            m = bake(job, args)
            if m:
                done.append(job["slug"])
                if not args.offline and not args.no_catalogs and job["slug"] != "mock":
                    try:
                        sys.path.insert(0, str(Path(__file__).resolve().parent))
                        import fetch_catalogs
                        fetch_catalogs.run(job["slug"])
                    except Exception as e:
                        log(f"  catalogues skipped: {e!r}")
        except Exception as e:
            log(f"  !! {job['slug']} failed: {e!r}")
    write_index()
    log(f"\nDone: {', '.join(done) or 'nothing'}")


def write_index():
    """frontend/public/data/index.json lists every baked target (used by the API and the static fallback)."""
    out = []
    for m in sorted(WEB_DATA.glob("*/manifest.json")):
        j = json.loads(m.read_text())
        out.append({"target": j["target"], "name": j["name"], "ra": j["ra"], "dec": j["dec"],
                    "fov": j["fov"], "source": j.get("source", "prebaked"),
                    "manifest": f"/data/{j['target']}/manifest.json"})
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "index.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
