"""Test: can we read only the pixels we need from NASA's public SPHEREx copy on Amazon S3,
instead of downloading IRSA cutouts? Answers the go/no-go question for "search any position".

For a few photos of a target we already made, it measures three ways of getting the same pixels:

  A. IRSA cutout service (what fetch_cutouts.py does today): one file with all 6 layers
  B. S3 + astropy ".section": reads the needed rows of IMAGE / FLAGS / VARIANCE (whole-width stripe)
  C. S3 + exact byte ranges: only the needed piece of each row, fetched in parallel

and checks that B and C give exactly the same pixel values as A. It prints time and megabytes for
each, and projects the cost of a whole new position.

Needs internet and:  pip install s3fs requests
    python science/test_partial_read.py --target wise0855 --n 6
    python science/test_partial_read.py --target wise0855 --n 6 --check-psf   # also: is EPSF the same in every photo?
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fetch_cutouts import CACHE, PIXEL_SCALE_DEG, WEB_DATA  # noqa: E402

BUCKET = "nasa-irsa-spherex"
LAYERS = ["IMAGE", "FLAGS", "VARIANCE"]  # what the viewer needs (ZODI is optional, EPSF unused)

STATS = {"bytes": 0, "requests": 0}


def count_s3_reads():
    """Count bytes and requests that s3fs really sends over the network."""
    from s3fs.core import S3File
    if getattr(S3File, "_counted", False):
        return
    orig = S3File._fetch_range

    def counted(self, start, end):
        data = orig(self, start, end)
        STATS["bytes"] += len(data)
        STATS["requests"] += 1
        return data

    S3File._fetch_range = counted
    S3File._counted = True


def s3_path(url):
    path = urlsplit(url).path
    return f"{BUCKET}/" + path.split("/ibe/data/spherex/", 1)[1]


def cutout_params(url):
    q = parse_qs(urlsplit(url).query)
    ra, dec = q["center"][0].rstrip("d").split(",")
    return float(ra), float(dec), float(q["size"][0])


def target_pixel(header, ra, dec):
    from astropy.wcs import WCS, FITSFixedWarning
    warnings.simplefilter("ignore", FITSFixedWarning)
    x, y = WCS(header).all_world2pix([[ra, dec]], 0)[0]
    return float(x), float(y)


def box(x, y, size_deg, nx, ny):
    half = int(math.ceil(size_deg / 2 / PIXEL_SCALE_DEG))
    xi, yi = int(round(x)), int(round(y))
    return max(0, xi - half), min(nx, xi + half + 1), max(0, yi - half), min(ny, yi + half + 1)


# --------------------------------------------------------------------------- the three methods

def method_a(url, cached):
    """IRSA cutout, the way we do it today. Re-downloads even if cached, to time it fairly."""
    import requests
    t0 = time.time()
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    dt = time.time() - t0
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".testA")
    tmp.write_bytes(r.content)
    return {"seconds": dt, "mb": len(r.content) / 1e6, "requests": 1, "file": tmp}


def method_b(fs, path, ra, dec, size):
    """astropy .section through s3fs: reads only the rows that hold our box."""
    from astropy.io import fits
    STATS.update(bytes=0, requests=0)
    t0 = time.time()
    out = {}
    with fs.open(path, "rb", block_size=1 << 20, cache_type="blockcache") as f:
        with fits.open(f, lazy_load_hdus=True) as hdul:
            hdr = hdul["IMAGE"].header
            ny, nx = hdr["NAXIS2"], hdr["NAXIS1"]
            x, y = target_pixel(hdr, ra, dec)
            x0, x1, y0, y1 = box(x, y, size, nx, ny)
            for name in LAYERS:
                out[name] = np.asarray(hdul[name].section[y0:y1, x0:x1])
            kinds = {h.name: type(h).__name__ for h in hdul}
            wl = None
            try:  # wavelength at the target, as the pipeline does
                from astropy.wcs import WCS
                swcs = WCS(hdr, fobj=hdul, key="W")
                swcs.sip = None
                w, _ = swcs.pixel_to_world(x, y)
                wl = float(w.to("um").value)
            except Exception as e:  # noqa: BLE001
                wl = f"failed: {e}"[:60]
    return {"seconds": time.time() - t0, "mb": STATS["bytes"] / 1e6, "requests": STATS["requests"],
            "data": out, "origin": (x0, y0), "target": (x, y), "full_shape": (ny, nx),
            "hdu_types": kinds, "wavelength_um": wl, "file_mb": fs.size(path) / 1e6}


def method_c(fs, path, ra, dec, size):
    """Exact byte ranges: only the box's piece of each row, all fetched in parallel."""
    from astropy.io import fits
    STATS.update(bytes=0, requests=0)
    t0 = time.time()
    plan = []
    with fs.open(path, "rb", block_size=1 << 16, cache_type="blockcache") as f:
        with fits.open(f, lazy_load_hdus=True) as hdul:
            hdr = hdul["IMAGE"].header
            ny, nx = hdr["NAXIS2"], hdr["NAXIS1"]
            x, y = target_pixel(hdr, ra, dec)
            x0, x1, y0, y1 = box(x, y, size, nx, ny)
            for name in LAYERS:
                h = hdul[name]
                if isinstance(h, fits.CompImageHDU):
                    return {"skipped": f"{name} is tile-compressed; byte ranges don't apply"}
                bpp = abs(h.header["BITPIX"]) // 8
                kind = "f" if h.header["BITPIX"] < 0 else "i"
                dtype = np.dtype(f">{kind}{bpp}")
                off = h._data_offset  # where this layer's pixels start in the file
                plan.append((name, off, bpp, dtype, h.header.get("BSCALE", 1), h.header.get("BZERO", 0)))
    header_bytes, header_reqs = STATS["bytes"], STATS["requests"]
    starts, ends, owners = [], [], []
    for name, off, bpp, *_ in plan:
        for row in range(y0, y1):
            s = off + (row * nx + x0) * bpp
            starts.append(s)
            ends.append(s + (x1 - x0) * bpp)
            owners.append(name)
    chunks = fs.cat_ranges([path] * len(starts), starts, ends)
    out = {}
    for name, _, _, dtype, bscale, bzero in plan:
        rows = [c for c, o in zip(chunks, owners) if o == name]
        a = np.frombuffer(b"".join(rows), dtype=dtype).reshape(y1 - y0, x1 - x0)
        out[name] = a * bscale + bzero if (bscale != 1 or bzero != 0) else a
    data_bytes = sum(e - s for s, e in zip(starts, ends))
    return {"seconds": time.time() - t0, "mb": (header_bytes + data_bytes) / 1e6,
            "requests": header_reqs + len(starts), "data": out, "origin": (x0, y0)}


# --------------------------------------------------------------------------- checks

def same_pixels(cutout_file, part, ra, dec):
    """Do the S3 pixels equal the IRSA cutout pixels at the same sky positions?"""
    from astropy.io import fits
    with fits.open(cutout_file) as h:
        res = {}
        hdr = h["IMAGE"].header
        xc, yc = target_pixel(hdr, ra, dec)
        xf, yf = part["target"]
        dx, dy = round(xf - xc), round(yf - yc)  # whole-pixel shift between cutout and full file
        if abs((xf - xc) - dx) > 0.01 or abs((yf - yc) - dy) > 0.01:
            return {"note": f"cutout is not a whole-pixel crop (shift {xf - xc:.3f}, {yf - yc:.3f})"}
        x0, y0 = part["origin"]
        for name in LAYERS:
            cut = h[name].data
            mine = part["data"][name]
            # cutout pixel (i, j) is full-file pixel (i + dy, j + dx) -> part index (i + dy - y0, j + dx - x0)
            i0, j0 = max(0, y0 - dy), max(0, x0 - dx)
            i1 = min(cut.shape[0], y0 - dy + mine.shape[0])
            j1 = min(cut.shape[1], x0 - dx + mine.shape[1])
            a = cut[i0:i1, j0:j1].astype(np.float64)
            b = mine[i0 + dy - y0:i1 + dy - y0, j0 + dx - x0:j1 + dx - x0].astype(np.float64)
            both = np.isfinite(a) & np.isfinite(b)
            res[name] = {"compared": int(both.sum()),
                         "identical": bool(np.array_equal(a[both], b[both]) and
                                           np.array_equal(np.isfinite(a), np.isfinite(b)))}
        layers = {x.name: round((x.data.nbytes if x.data is not None else 0) / 1e6, 2) for x in h}
    return {"per_layer": res, "cutout_layers_mb": layers}


def check_psf(fs, rows):
    """Is EPSF identical between two photos from the same detector?"""
    from astropy.io import fits
    by_det = {}
    for r in rows:
        by_det.setdefault(r["detector"], []).append(r)
    for det, rs in sorted(by_det.items()):
        if len(rs) < 2:
            continue
        psfs = []
        for r in (rs[0], rs[-1]):
            with fs.open(s3_path(r["url"]), "rb", block_size=1 << 22) as f, fits.open(f) as h:
                name = next((x.name for x in h if "PSF" in x.name), None)
                psfs.append((r["date"], name, None if name is None else np.array(h[name].data)))
        (d1, n1, p1), (d2, n2, p2) = psfs
        if p1 is None or p2 is None:
            print(f"  D{det}: no PSF layer found ({n1}, {n2})")
            continue
        same = p1.shape == p2.shape and np.array_equal(p1, p2)
        diff = None if same or p1.shape != p2.shape else float(np.nanmax(np.abs(p1 - p2)) / np.nanmax(np.abs(p1)))
        print(f"  D{det}: {d1} vs {d2}: shape {p1.shape}, identical={same}"
              + ("" if diff is None else f", max difference {diff:.1%} of peak"))
        return


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", default="wise0855")
    p.add_argument("--n", type=int, default=6, help="how many photos to test (spread over dates and detectors)")
    p.add_argument("--skip-irsa", action="store_true", help="don't re-download from IRSA; compare with the cache")
    p.add_argument("--check-psf", action="store_true")
    args = p.parse_args()

    import s3fs
    count_s3_reads()
    fs = s3fs.S3FileSystem(anon=True)

    rows = json.loads((WEB_DATA / args.target / "exposures.json").read_text())
    pick = [rows[round(i * (len(rows) - 1) / max(1, args.n - 1))] for i in range(args.n)]
    print(f"{args.target}: {len(rows)} photos in the archive for this field; testing {len(pick)}\n")

    results = []
    for r in pick:
        ra, dec, size = cutout_params(r["url"])
        path = s3_path(r["url"])
        cached = CACHE / args.target / r["file"]
        print(f"- {r['date']} D{r['detector']}  s3://{path.split('/', 1)[1][:70]}...")
        row = {}
        try:
            if args.skip_irsa:
                if not cached.exists():
                    print("    no cached cutout to compare with; run without --skip-irsa")
                    continue
                row["A"] = {"seconds": float("nan"), "mb": cached.stat().st_size / 1e6, "requests": 1, "file": cached}
            else:
                row["A"] = method_a(r["url"], cached)
            row["B"] = method_b(fs, path, ra, dec, size)
            row["C"] = method_c(fs, path, ra, dec, size)
        except FileNotFoundError:
            print("    NOT FOUND on S3 (this release may not be mirrored there yet)")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"    failed: {type(e).__name__}: {e}")
            continue
        b, c, a = row["B"], row["C"], row["A"]
        print(f"    full file {b['file_mb']:.1f} MB; layers: {b['hdu_types']}")
        print(f"    wavelength at target: {b['wavelength_um']}")
        for k in "ABC":
            m = row[k]
            if "skipped" in m:
                print(f"    {k}: skipped ({m['skipped']})")
                continue
            print(f"    {k}: {m['seconds']:6.2f} s  {m['mb']:6.2f} MB  {m['requests']:5d} requests")
        for k in "BC":
            if "data" in row[k]:
                chk = same_pixels(a["file"], {**row[k], "target": b["target"]}, ra, dec)
                print(f"    {k} vs IRSA cutout: {chk.get('per_layer', chk)}")
                if k == "B":
                    print(f"    IRSA cutout layer sizes (MB): {chk.get('cutout_layers_mb')}")
        if not args.skip_irsa:
            a["file"].unlink(missing_ok=True)
        results.append(row)

    if not results:
        print("\nNothing measured.")
        return
    n_all = len(rows)
    print("\nSummary (average per photo, and a whole new position with 8 downloads in parallel):")
    for k, label in [("A", "IRSA cutout (today)"), ("B", "S3 rows (.section)"), ("C", "S3 exact ranges")]:
        ms = [r[k] for r in results if "skipped" not in r[k] and np.isfinite(r[k]["seconds"])]
        if not ms:
            continue
        s = np.mean([m["seconds"] for m in ms])
        mb = np.mean([m["mb"] for m in ms])
        print(f"  {label:22s} {s:5.2f} s  {mb:6.2f} MB   ->  all {n_all} photos: ~{n_all * s / 8 / 60:4.1f} min,"
              f" {n_all * mb / 1000:4.2f} GB   |   60 photos: ~{60 * s / 8:4.0f} s, {60 * mb:4.0f} MB")
    if args.check_psf:
        print("\nEPSF check (same detector, first vs last date):")
        check_psf(fs, rows)


if __name__ == "__main__":
    main()
