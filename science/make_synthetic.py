#!/usr/bin/env python3
"""
Make fake SPHEREx-shaped cutouts (IMAGE, FLAGS, VARIANCE, ZODI, PSF, WCS-WAVE-less) for offline testing.

    python science/make_synthetic.py            # writes science/cache/mock/ + index.json
    python science/fetch_cutouts.py --ra 133.795 --dec -7.245 --slug mock --size 0.2 \
        --offline --pmra -8000 --pmdec 30000

The field has ~60 static stars, one fast mover (exaggerated: ~31"/yr so it is obvious)
and one variable star. Four survey passes, six detectors, three exposures each.
NOT real data: the frontend labels the 'mock' target as synthetic.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "science" / "cache" / "mock"
RA0, DEC0 = 133.795, -7.245
PIX = 6.15 / 3600
N = 140  # cutout pixels (a bit larger than the 0.2 deg grid so reprojection has margin)
PM = (-8000.0, 30000.0)  # mas/yr, exaggerated
EPOCHS_MJD = [60798.0, 60982.0, 61163.0, 61340.0]  # ~May 2025, Nov 2025, May 2026, Nov 2026
VAR_AMP = [1.0, 2.2, 0.6, 1.6]
rng = np.random.default_rng(42)

STARS = [(RA0 + rng.uniform(-0.11, 0.11) / math.cos(math.radians(DEC0)),
          DEC0 + rng.uniform(-0.11, 0.11), 10 ** rng.uniform(-0.5, 1.5)) for _ in range(60)]
VAR_STAR = (RA0 + 0.045, DEC0 - 0.03, 6.0)
MSK = {0: "TRANSIENT", 1: "OVERFLOW", 2: "SUR_ERROR", 6: "NONFUNC", 9: "MISSING_DATA",
       10: "HOT", 11: "COLD", 15: "NONLINEAR", 17: "PERSIST", 19: "OUTLIER", 21: "SOURCE"}


def mover_pos(mjd):
    yr = (mjd - 51544.5) / 365.25
    dra = PM[0] * yr / 3.6e6 / math.cos(math.radians(DEC0))
    ddec = PM[1] * yr / 3.6e6
    # anchor so the mover sits near the centre in 2026.0
    yr26 = 26.0
    return (RA0 + dra - PM[0] * yr26 / 3.6e6 / math.cos(math.radians(DEC0)),
            DEC0 + ddec - PM[1] * yr26 / 3.6e6)


def add_psf(img, x, y, flux, sigma=0.9):
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    img += flux * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2))


def one(mjd, det, k):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    jitter = rng.normal(0, 0.01, 2)
    w.wcs.crval = [RA0 + jitter[0], DEC0 + jitter[1]]
    w.wcs.crpix = [N / 2, N / 2]
    rot = math.radians(rng.uniform(0, 360))  # SPHEREx frames are not north-up
    c, s = math.cos(rot), math.sin(rot)
    w.wcs.cd = np.array([[-c, s], [s, c]]) * PIX
    img = np.zeros((N, N))
    for ra, dec, f in STARS:
        x, y = w.world_to_pixel_values(ra, dec)
        add_psf(img, x, y, f * (0.6 + 0.15 * det))
    mra, mdec = mover_pos(mjd)
    x, y = w.world_to_pixel_values(mra, mdec)
    add_psf(img, x, y, 2.0 + 1.5 * det)  # brighter at long wavelengths, like a brown dwarf
    x, y = w.world_to_pixel_values(*VAR_STAR[:2])
    ep = min(range(4), key=lambda i: abs(EPOCHS_MJD[i] - mjd))
    add_psf(img, x, y, VAR_STAR[2] * VAR_AMP[ep])
    zodi = np.full((N, N), 0.4 + 0.1 * det) + np.linspace(0, 0.05, N)[None, :]
    noise = 0.12
    img = img + zodi + rng.normal(0, noise, img.shape)
    flags = np.zeros((N, N), np.int32)
    cr = rng.integers(0, N, (6, 2))  # cosmic rays
    for (a, b) in cr:
        img[a, b] += 40
        flags[a, b] |= 1 << 0
    flags[rng.integers(0, N, 4), rng.integers(0, N, 4)] |= 1 << 10
    var = np.full((N, N), noise ** 2)

    ph = fits.PrimaryHDU()
    ph.header["VERSION"] = "synthetic-1"
    ih = fits.ImageHDU(img.astype(np.float32), header=w.to_header(), name="IMAGE")
    ih.header["BUNIT"] = "MJy/sr"
    fh = fits.ImageHDU(flags, name="FLAGS")
    for bit, name in MSK.items():
        fh.header[f"MSKN{bit:04d}"] = name
    vh = fits.ImageHDU(var.astype(np.float32), name="VARIANCE")
    zh = fits.ImageHDU(zodi.astype(np.float32), name="ZODI")
    return fits.HDUList([ph, ih, fh, vh, zh])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for e, m0 in enumerate(EPOCHS_MJD):
        for det in range(1, 7):
            for k in range(3):
                mjd = m0 + det * 0.4 + k * 0.9
                url = f"synthetic://mock/{e}/{det}/{k}"
                fn = hashlib.sha1(url.encode()).hexdigest()[:16] + ".fits"
                one(mjd, det, k).writeto(OUT / fn, overwrite=True)
                rows.append({"url": url, "raw_uri": url, "mjd": mjd, "detector": det,
                             "bandpass": f"SPHEREx-D{det}", "file": fn})
    (OUT / "index.json").write_text(json.dumps({"ra": RA0, "dec": DEC0, "size": 0.2,
                                                "synthetic": True, "rows": rows}, indent=1))
    print(f"wrote {len(rows)} synthetic cutouts to {OUT}")


if __name__ == "__main__":
    main()
