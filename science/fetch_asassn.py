"""
science/fetch_asassn.py  -  download the RW Aur ASAS-SN light curve to data/rwaur_external.csv

Run (from repo root):
    pip install skypatrol
    python science/fetch_asassn.py
    python science/rwaur_answer_key.py --external data/rwaur_external.csv --band g

ASAS-SN has used g-band since 2018, so use --band g.
"""
import os
import sys

import numpy as np
import pandas as pd

RA, DEC = 76.956, 30.401
EPOCHS = {0: (60919, 60938), 1: (61091, 61111), 2: (61285, 61299)}   # MJD ranges of the 3 SPHEREx epochs


def main():
    from pyasassn.client import SkyPatrolClient
    client = SkyPatrolClient(verbose=False)
    lcs = client.cone_search(ra_deg=RA, dec_deg=DEC, radius=15, units="arcsec",
                             catalog="master_list", download=True)
    info = lcs.catalog_info
    if len(info) == 0:
        raise SystemExit("ASAS-SN returned no target near RW Aur.")
    d2 = (info["ra_deg"] - RA) ** 2 + ((info["dec_deg"] - DEC)) ** 2
    best = info.loc[d2.idxmin(), "asas_sn_id"]
    df = lcs.data[lcs.data["asas_sn_id"] == best].copy()
    print("ASAS-SN id:", best, "| rows:", len(df))

    df = df[(df["mag_err"] < 1) & (df["mag"] < 30)]
    if "quality" in df.columns:
        df = df[df["quality"].astype(str).str.upper() == "G"]
    out = pd.DataFrame({"jd": df["jd"], "mag": df["mag"], "mag_err": df["mag_err"], "band": df["phot_filter"]})
    out = out.sort_values("jd")
    os.makedirs("data", exist_ok=True)
    out.to_csv("data/rwaur_external.csv", index=False)
    print("wrote data/rwaur_external.csv:", len(out), "good points; bands:", out["band"].value_counts().to_dict())

    mjd = out["jd"] - 2400000.5
    for k, (lo, hi) in EPOCHS.items():
        s = out[(mjd >= lo - 7) & (mjd <= hi + 7)]
        print(f"epoch {k}: {len(s)} points", f"median mag {s['mag'].median():.2f}" if len(s) else "(none)")
    if len(out) and mjd.max() < 60900:
        print("WARNING: no data after Sept 2025 in this file.")


if __name__ == "__main__":
    sys.exit(main())