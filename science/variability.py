"""
science/variability.py  -  Variable-star flagging (Fatma)

Idea: measure many Gaia stars (known variable / not variable) in the SAME SPHEREx
exposures, compare each star only to ITSELF at matched wavelength on different days,
tune the threshold on steady stars, test on stars held back.

Run:
    pip install astropy astroquery scipy pandas numpy
    python science/variability.py --ra 76.956526 --dec 30.401438 --slug rwaur --max-obs 40
"""
import argparse, json, os, time
import numpy as np
import pandas as pd
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy import log as _alog
_alog.setLevel("WARNING")   # silence the harmless SIP INFO spam
from astropy.wcs.utils import proj_plane_pixel_area
from astropy.utils.data import conf
from astroquery.ipac.irsa import Irsa
from astroquery.vizier import Vizier

conf.remote_timeout = 120

BAD_BITS = [0, 1, 2, 6, 7, 9, 10, 11, 15, 17, 19, 20, 22, 23, 24, 25, 26, 27, 28]
BAD_MASK = sum(1 << b for b in BAD_BITS)
AP_R, ANN_IN, ANN_OUT = 2.0, 4.0, 7.0
LOG_BIN = 0.02          # wavelength bin = 2% wide (about one SPHEREx passband)
MIN_SNR = 20            # only stars bright enough to measure well


# ---------------------------------------------------------------- 1. star list
def build_stars(target, radius_deg, gmax, n_steady, rng):
    from gaia_utils import gaia_cone
    df = gaia_cone(target, radius_deg)
    df = df[(df["Gmag"] > 7) & (df["Gmag"] < gmax)].copy()
    df["VarFlag"] = df["VarFlag"].astype(str).str.strip()
    var = df[df["VarFlag"] == "VARIABLE"]
    steady = df[df["VarFlag"] != "VARIABLE"]
    steady = steady.sample(min(n_steady, len(steady)), random_state=int(rng.integers(1e9)))
    stars = pd.concat([var.assign(label="variable"), steady.assign(label="steady")])
    stars = stars.rename(columns={"RA_ICRS": "ra", "DE_ICRS": "dec", "Source": "star_id"})
    stars["star_id"] = stars["star_id"].astype(str)
    return stars[["star_id", "ra", "dec", "Gmag", "label"]].reset_index(drop=True)


# ---------------------------------------------------------------- 2. photometry
def photometry(img, var, flg, x, y):
    x0, y0 = int(round(x)), int(round(y))
    r = int(ANN_OUT) + 2
    ys, xs = slice(max(0, y0 - r), y0 + r + 1), slice(max(0, x0 - r), x0 + r + 1)
    im, va, fl = img[ys, xs], var[ys, xs], flg[ys, xs]
    yy, xx = np.indices(im.shape)
    yy = yy + ys.start
    xx = xx + xs.start
    d = np.hypot(xx - x, yy - y)
    ok = np.isfinite(im) & np.isfinite(va) & (va >= 0) & ((fl & BAD_MASK) == 0)
    ap, an = (d <= AP_R) & ok, (d >= ANN_IN) & (d <= ANN_OUT) & ok
    if ap.sum() < 8 or an.sum() < 15:
        return None
    bkg = np.median(im[an])
    sig = 1.4826 * np.median(np.abs(im[an] - bkg))
    net = np.sum(im[ap] - bkg)
    err = np.sqrt(np.sum(va[ap]) + ap.sum() * (sig / np.sqrt(an.sum())) ** 2)
    return net, err


def measure_all(selected, stars):
    coords = SkyCoord(stars["ra"].values, stars["dec"].values, unit="deg")
    rows = []
    for k, row in enumerate(selected):
        print(f"[{k + 1}/{len(selected)}] {row['obs_id']}")
        try:
            with fits.open(row["access_url"], memmap=False) as h:
                img, var, flg = h["IMAGE"].data, h["VARIANCE"].data, h["FLAGS"].data
                wcs = WCS(h["IMAGE"].header).celestial
                swcs = WCS(h["IMAGE"].header, fobj=h, key="W")
                swcs.sip = None
                area_sr = proj_plane_pixel_area(wcs) * (np.pi / 180) ** 2
                px, py = wcs.world_to_pixel(coords)
                H, W = img.shape
                for i in range(len(stars)):
                    if not (np.isfinite(px[i]) and np.isfinite(py[i])):
                        continue
                    if not (10 < px[i] < W - 10 and 10 < py[i] < H - 10):
                        continue
                    m = photometry(img, var, flg, px[i], py[i])
                    if m is None:
                        continue
                    wl, bw = swcs.pixel_to_world(px[i], py[i])
                    rows.append({
                        "star_id": stars["star_id"][i],
                        "obs_id": row["obs_id"],
                        "mjd": float(row["t_min"]),
                        "wavelength_um": wl.to_value(u.um),
                        "bandwidth_um": bw.to_value(u.um),
                        "flux_Jy": m[0] * area_sr * 1e6,
                        "err_Jy": m[1] * area_sr * 1e6,
                    })
        except Exception as e:
            print("   skipped:", e)
        time.sleep(1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3. variability metric
def star_metric(g):
    """Compare a star only to itself, same wavelength bin, different days."""
    g = g.copy()
    g["bin"] = np.floor(np.log(g["wavelength_um"]) / LOG_BIN).astype(int)
    g["day"] = np.floor(g["mjd"]).astype(int)
    rel = []
    for _, b in g.groupby("bin"):
        b = b.drop_duplicates("day")
        if len(b) >= 2 and b["flux_Jy"].mean() > 0:
            rel.append(np.std(b["flux_Jy"], ddof=1) / b["flux_Jy"].mean())
    if not rel:
        return None
    return {"rms_rel": float(np.sqrt(np.mean(np.square(rel)))), "n_bins": len(rel),
            "n_meas": len(g), "median_snr": float((g["flux_Jy"] / g["err_Jy"]).median())}


# ---------------------------------------------------------------- 4. main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", type=float, default=76.956526)
    ap.add_argument("--dec", type=float, default=30.401438)
    ap.add_argument("--slug", default="rwaur")
    ap.add_argument("--radius", type=float, default=0.15, help="star search radius, deg")
    ap.add_argument("--gmax", type=float, default=14.0)
    ap.add_argument("--n-steady", type=int, default=60)
    ap.add_argument("--max-obs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    outdir = f"science/output/{a.slug}"
    os.makedirs(outdir, exist_ok=True)

    target = SkyCoord(a.ra, a.dec, unit="deg")
    stars = build_stars(target, a.radius, a.gmax, a.n_steady, rng)
    print(stars["label"].value_counts().to_dict())
    stars.to_csv(f"{outdir}/variable_truth.csv", index=False)

    res = Irsa.query_sia(pos=(target, 1 * u.arcsec), collection=["spherex_dr1", "spherex_qr3"])
    res = res[np.argsort(res["t_min"])]
    if len(res) > a.max_obs:
        res = res[np.linspace(0, len(res) - 1, a.max_obs, dtype=int)]
    print("exposures:", len(res))

    meas = measure_all(res, stars)
    meas.to_csv(f"{outdir}/star_measurements.csv", index=False)

    # per-star metric
    out = []
    for sid, g in meas.groupby("star_id"):
        m = star_metric(g)
        if m and m["median_snr"] >= MIN_SNR:
            out.append({"star_id": sid, **m})
    res_df = pd.DataFrame(out).merge(stars, on="star_id")
    print("stars with usable metric:", res_df["label"].value_counts().to_dict())

    # split 50/50 tune vs held-out, inside each class
    res_df["split"] = "tune"
    for lab in ["variable", "steady"]:
        idx = res_df.index[res_df["label"] == lab].to_numpy().copy()
        rng.shuffle(idx)
        res_df.loc[idx[len(idx) // 2:], "split"] = "heldout"

    # threshold = 95th percentile of steady stars in tune split (5% false-alarm target)
    steady_tune = res_df[(res_df.label == "steady") & (res_df.split == "tune")]["rms_rel"]
    threshold = float(np.percentile(steady_tune, 95)) if len(steady_tune) >= 5 else float("nan")
    res_df["flagged"] = res_df["rms_rel"] > threshold
    res_df.to_csv(f"{outdir}/variability_results.csv", index=False)

    ho = res_df[res_df.split == "heldout"]
    v, s = ho[ho.label == "variable"], ho[ho.label == "steady"]
    summary = {
        "method": "same-star, same-wavelength-bin, different-day relative scatter; "
                  "threshold = 95th percentile of steady stars (tuning half)",
        "threshold_rel_rms": threshold,
        "heldout_variables": int(len(v)),
        "heldout_variables_caught": int(v["flagged"].sum()),
        "heldout_steady": int(len(s)),
        "heldout_false_alarms": int(s["flagged"].sum()),
        "recall": float(v["flagged"].mean()) if len(v) else None,
        "false_alarm_rate": float(s["flagged"].mean()) if len(s) else None,
        "note": "formal prototype numbers; Gaia VarFlag labels; small sample",
    }
    print(json.dumps(summary, indent=2))
    json.dump(summary, open(f"{outdir}/variability_summary.json", "w"), indent=2)

    # merge into detections.json next to the manifest (if it exists)
    det = f"frontend/public/data/{a.slug}/detections.json"
    d = json.load(open(det)) if os.path.exists(det) else {}
    d["variability"] = {
        "summary": summary,
        "stars": res_df[["star_id", "ra", "dec", "Gmag", "label", "rms_rel", "flagged"]]
                 .round(5).to_dict("records"),
    }
    os.makedirs(os.path.dirname(det), exist_ok=True)
    json.dump(d, open(det, "w"), indent=2)
    print("wrote", det)


if __name__ == "__main__":
    main()