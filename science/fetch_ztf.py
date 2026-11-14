"""
science/fetch_ztf.py  -  RW Aur light curve from ZTF (via IRSA) -> data/rwaur_ztf.csv

Why: the ASAS-SN file we could fetch ends in Feb 2025, before our first SPHEREx epoch (Sep 2025).
ZTF public data may cover later dates (the end date depends on the latest ZTF data release).

Run (from repo root):
    python science/fetch_ztf.py
    python science/rwaur_answer_key.py --external data/rwaur_ztf.csv --band r      # or --band g
"""
import io
import os
import sys

import pandas as pd
import requests

RA, DEC = 76.956, 30.401
RADIUS_DEG = 0.0006          # ~2 arcsec
URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves"
EPOCHS = {0: (60919, 60938), 1: (61091, 61111), 2: (61285, 61299)}   # MJD ranges of the SPHEREx epochs
SATURATION_WARN_MAG = 12.5   # ZTF saturates around here: brighter points are unreliable


def fetch_band(band):
    params = {"POS": f"CIRCLE {RA} {DEC} {RADIUS_DEG}", "BANDNAME": band, "FORMAT": "csv"}
    r = requests.get(URL, params=params, timeout=180)
    r.raise_for_status()
    if not r.text.strip() or "oid" not in r.text.splitlines()[0].lower():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(r.text))


def clean(df, band):
    if df.empty:
        return df
    df = df[(df["catflags"] == 0) & (df["magerr"] < 0.3)].copy()
    return pd.DataFrame({"jd": df["mjd"] + 2400000.5, "mag": df["mag"], "mag_err": df["magerr"], "band": band})


def main():
    parts = []
    for band in ["g", "r"]:
        try:
            raw = fetch_band(band)
        except Exception as e:
            print(f"band {band}: request failed: {e}")
            continue
        c = clean(raw, band)
        print(f"band {band}: {len(raw)} rows, {len(c)} good")
        if len(c):
            parts.append(c)
    if not parts:
        raise SystemExit("No ZTF data returned for RW Aur.")
    out = pd.concat(parts).sort_values("jd")
    os.makedirs("data", exist_ok=True)
    out.to_csv("data/rwaur_ztf.csv", index=False)
    mjd = out["jd"] - 2400000.5
    print(f"wrote data/rwaur_ztf.csv: {len(out)} points, MJD {mjd.min():.0f} -> {mjd.max():.0f}")
    for band in ["g", "r"]:
        b = out[out["band"] == band]
        mb = b["jd"] - 2400000.5
        for k, (lo, hi) in EPOCHS.items():
            s = b[(mb >= lo - 7) & (mb <= hi + 7)]
            txt = f"{len(s)} points, median mag {s['mag'].median():.2f}" if len(s) else "none"
            print(f"  {band}-band, epoch {k}: {txt}")
    if (out["mag"] < SATURATION_WARN_MAG).any():
        print(f"NOTE: some points are brighter than {SATURATION_WARN_MAG} mag; ZTF may be saturated there.")
    if mjd.max() < 60900:
        print("WARNING: no data after Sept 2025 in this file.")


if __name__ == "__main__":
    sys.exit(main())
    