"""
science/rwaur_answer_key.py  -  RW Aurigae: external "bright/faint" answer key vs SPHEREx

What it does
  1. Reads an external light curve (AAVSO / ASAS-SN CSV you download) and labels each SPHEREx
     epoch as bright / faint / intermediate  ->  rwaur_answer_key.csv
  2. Measures RW Aur in SPHEREx cutouts (from exposures.json) at MATCHED wavelength across epochs,
     calibrated by steady Gaia stars in the same two exposures (ensemble)  ->  rwaur_pair_results.csv
  3. Compares direction (brighter / fainter / no change) between SPHEREx and the external data
     ->  rwaur_summary.json  with one slide sentence.

Run (from repo root):
    python science/rwaur_answer_key.py --external data/rwaur_asassn.csv --band V
    python science/rwaur_answer_key.py                      # SPHEREx side only (no external file yet)
"""
import argparse, json, os, sys, time
import numpy as np
import pandas as pd
import requests
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy import log as _alog
_alog.setLevel("WARNING")   # silence the harmless SIP INFO spam

SLUG = "rw-aur"
TARGET_RA, TARGET_DEC = 76.956, 30.401
AP_R, ANN_IN, ANN_OUT = 3.0, 5.0, 8.0          # pixels (6.15"/px)
# bad-pixel bits from the IRSA tutorial list, WITHOUT OVERFLOW(1) and NONLINEAR(19)
# so bright stars are not cut into holes (same policy as the README); they are counted instead.
BAD_BITS = [0, 2, 6, 7, 9, 10, 11, 15, 17, 20, 22, 23, 24, 25, 26, 27, 28]
BAD_MASK = sum(1 << b for b in BAD_BITS)
SAT_MASK = (1 << 1) | (1 << 19)
EPOCH_PAIRS = [(0, 1), (1, 2), (0, 2)]
MAG_STEADY = 0.10        # external change smaller than this (mag) counts as "no change"
MAX_SAT_PIXELS = 5          # mean saturated pixels per aperture above this = unreliable
MIN_REL_THRESHOLD = 0.05  # SPHEREx change must exceed 5% and 3x steady-star scatter


# ============================================================ external data
def parse_external(path, band=None):
    df = pd.read_csv(path, comment="#")
    low = {c.lower().strip(): c for c in df.columns}
    tcol = next((low[k] for k in ["mjd", "hjd", "jd", "date", "time"] if k in low), None)
    mcol = next((low[k] for k in ["mag", "magnitude", "v", "g_mag"] if k in low), None)
    if tcol is None or mcol is None:
        raise SystemExit(f"Can't find time/mag columns in {path}. Columns: {list(df.columns)}")
    out = pd.DataFrame({"t": pd.to_numeric(df[tcol], errors="coerce"),
                        "mag": pd.to_numeric(df[mcol], errors="coerce")})
    if band:
        bcol = next((low[k] for k in ["band", "filter"] if k in low), None)
        if bcol is not None:
            out = out[df[bcol].astype(str).str.strip().str.upper() == band.upper()]
    ecol = next((low[k] for k in ["mag_err", "uncertainty", "magerr"] if k in low), None)
    if ecol is not None:
        err = pd.to_numeric(df.loc[out.index, ecol], errors="coerce")
        out = out[~(err > 0.3)]
    out = out.dropna()
    out = out[(out["mag"] > 0) & (out["mag"] < 30)]
    if out["t"].median() > 2.4e6:           # JD / HJD -> MJD
        out["t"] = out["t"] - 2400000.5
    elif out["t"].median() < 1e5 and out["t"].median() > 0:
        pass                                  # already MJD
    return out.sort_values("t").reset_index(drop=True)


def epoch_external(ext, mjd_lo, mjd_hi, pad=7):
    s = ext[(ext["t"] >= mjd_lo - pad) & (ext["t"] <= mjd_hi + pad)]
    if len(s) < 3:
        return None, len(s)
    return float(s["mag"].median()), len(s)


def label_state(mag, base_median, tol=0.15):
    if mag is None:
        return "no_external_data"
    if mag < base_median - tol:
        return "bright"
    if mag > base_median + tol:
        return "faint"
    return "intermediate"


def direction_from_dmag(dmag):
    if dmag < -MAG_STEADY:
        return "brighter"
    if dmag > MAG_STEADY:
        return "fainter"
    return "no_change"


# ============================================================ SPHEREx side
def load_exposures():
    path = f"frontend/public/data/{SLUG}/exposures.json"
    return pd.DataFrame(json.load(open(path)))


def band_overlap(w1, b1, w2, b2):
    lo = max(w1 - b1 / 2, w2 - b2 / 2)
    hi = min(w1 + b1 / 2, w2 + b2 / 2)
    return max(0.0, hi - lo) / min(b1, b2)


def pick_pairs(exps, n_pairs):
    chosen = []
    for ea, eb in EPOCH_PAIRS:
        A, B = exps[exps.epoch == ea], exps[exps.epoch == eb]
        cands = []
        for ia, a in A.iterrows():
            for ib, b in B.iterrows():
                if a.detector != b.detector:
                    continue
                ov = band_overlap(a.wavelength_um, a.bandwidth_um, b.wavelength_um, b.bandwidth_um)
                if ov >= 0.5:
                    cands.append((ov, ia, ib))
        cands.sort(reverse=True)
        used_a, used_b, k = set(), set(), 0
        for ov, ia, ib in cands:
            if ia in used_a or ib in used_b:
                continue
            used_a.add(ia); used_b.add(ib)
            chosen.append((ea, eb, ia, ib, ov)); k += 1
            if k >= n_pairs:
                break
        print(f"epoch {ea}->{eb}: {len(cands)} matched candidates, using {k}")
    return chosen


def download(row, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, row["file"])
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    for attempt in range(3):
        try:
            r = requests.get(row["url"], timeout=180)
            r.raise_for_status()
            open(path, "wb").write(r.content)
            return path
        except Exception as e:
            print("   download retry", attempt + 1, e)
            time.sleep(3)
    return None


def aper(img, var, flg, x, y):
    x0, y0 = int(round(x)), int(round(y))
    r = int(ANN_OUT) + 2
    ys, xs = slice(max(0, y0 - r), y0 + r + 1), slice(max(0, x0 - r), x0 + r + 1)
    im, va, fl = img[ys, xs], var[ys, xs], flg[ys, xs]
    if im.size == 0:
        return None
    yy, xx = np.indices(im.shape)
    d = np.hypot(xx + xs.start - x, yy + ys.start - y)
    ok = np.isfinite(im) & np.isfinite(va) & (va >= 0) & ((fl & BAD_MASK) == 0)
    ap_all, ap = d <= AP_R, (d <= AP_R) & ok
    an = (d >= ANN_IN) & (d <= ANN_OUT) & ok
    if ap.sum() < 0.7 * ap_all.sum() or an.sum() < 20:
        return None
    bkg = np.median(im[an])
    sig = 1.4826 * np.median(np.abs(im[an] - bkg))
    net = float(np.sum(im[ap] - bkg))
    err = float(np.sqrt(np.sum(va[ap]) + ap.sum() * (sig / np.sqrt(an.sum())) ** 2))
    sat = int(np.sum((fl[ap_all] & SAT_MASK) != 0))
    return net, err, sat


_warned = {"wave": False}


def measure_exposure(path, coords):
    """Return dict of arrays (one entry per coord): flux, err, sat, wl, bw. NaN = not measurable."""
    n = len(coords)
    out = {k: np.full(n, np.nan) for k in ["flux", "err", "sat", "wl", "bw"]}
    with fits.open(path, memmap=False) as h:
        hdr = h["IMAGE"].header
        img = np.asarray(h["IMAGE"].data, dtype=float)
        var = np.asarray(h["VARIANCE"].data, dtype=float)
        flg = np.asarray(h["FLAGS"].data, dtype=np.int64)
        wcs = WCS(hdr).celestial
        try:
            swcs = WCS(hdr, fobj=h, key="W")
            swcs.sip = None
        except Exception:
            swcs = None
    px, py = wcs.world_to_pixel(coords)
    H, W = img.shape
    inside = np.isfinite(px) & np.isfinite(py) & (px > 12) & (px < W - 12) & (py > 12) & (py < H - 12)
    for i in np.where(inside)[0]:
        m = aper(img, var, flg, px[i], py[i])
        if m is not None:
            out["flux"][i], out["err"][i], out["sat"][i] = m
    if swcs is not None:
        try:
            wl, bw = swcs.pixel_to_world(np.where(inside, px, 0), np.where(inside, py, 0))
            out["wl"] = np.where(inside, wl.to_value(u.um), np.nan)
            out["bw"] = np.where(inside, bw.to_value(u.um), np.nan)
        except Exception as e:
            if not _warned["wave"]:
                print("   WARNING spectral WCS failed:", e); _warned["wave"] = True
    elif not _warned["wave"]:
        print("   WARNING: no spectral WCS in cutout -> ensemble cannot be wavelength-matched")
        _warned["wave"] = True
    return out


def gaia_steady_stars(target, radius_deg=0.3, gmax=13.5, n=80):
    from gaia_utils import gaia_cone
    df = gaia_cone(target, radius_deg)
    df["VarFlag"] = df["VarFlag"].astype(str).str.strip()
    pm = np.hypot(df["pmRA"].fillna(0), df["pmDE"].fillna(0))
    df = df[(df["Gmag"] > 8) & (df["Gmag"] < gmax) & (df["VarFlag"] != "VARIABLE") & (pm < 100)]
    sep = SkyCoord(df["RA_ICRS"].values, df["DE_ICRS"].values, unit="deg").separation(target).arcsec
    df = df[sep > 45].sort_values("Gmag").head(n)
    return SkyCoord(df["RA_ICRS"].values, df["DE_ICRS"].values, unit="deg")


def analyse_pair(ma, mb, min_stars=5):
    """ma, mb: measure_exposure outputs; index 0 = RW Aur, 1: = steady stars."""
    fa, fb = ma["flux"], mb["flux"]
    if not (fa[0] > 0 and fb[0] > 0) or fa[0] / ma["err"][0] < 10 or fb[0] / mb["err"][0] < 10:
        return None
    ratios = []
    for i in range(1, len(fa)):
        if not (fa[i] > 0 and fb[i] > 0) or np.isnan(ma["wl"][i]) or np.isnan(mb["wl"][i]):
            continue
        if fa[i] / ma["err"][i] < 20 or fb[i] / mb["err"][i] < 20:
            continue
        if band_overlap(ma["wl"][i], ma["bw"][i], mb["wl"][i], mb["bw"][i]) < 0.5:
            continue
        ratios.append(fb[i] / fa[i])
    if len(ratios) < min_stars:
        return None
    ratios = np.array(ratios)
    ens = float(np.median(ratios))
    scat = float(1.4826 * np.median(np.abs(ratios - ens)) / ens)
    raw = fb[0] / fa[0]
    return {"ratio_raw": float(raw), "ens_ratio": ens, "ratio_corr": float(raw / ens),
            "star_scatter_rel": scat, "n_stars": len(ratios),
            "saturated_pixels": int(np.nansum([ma["sat"][0], mb["sat"][0]]))}


def classify_pair(s):
    """s = rows of pair results for one epoch pair. Returns dict with direction (or 'inconclusive')."""
    ratios = s["ratio_corr"].to_numpy(dtype=float)
    med = float(np.median(ratios))
    change = med - 1
    thr = max(MIN_REL_THRESHOLD, 3 * float(np.median(s["star_scatter_rel"])))
    spread = float(1.4826 * np.median(np.abs(ratios - med)))        # pair-to-pair disagreement
    sat_mean = float(s["saturated_pixels"].mean())
    if spread > thr or sat_mean > MAX_SAT_PIXELS:
        direction = "inconclusive"
    else:
        direction = "brighter" if change > thr else "fainter" if change < -thr else "no_change"
    return {"change": change, "thr": thr, "spread": spread, "sat_mean": sat_mean, "direction": direction}


# ============================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", help="CSV light curve of RW Aur (AAVSO / ASAS-SN)")
    ap.add_argument("--band", default=None, help="filter to keep, e.g. V")
    ap.add_argument("--pairs", type=int, default=6, help="exposure pairs per epoch pair")
    a = ap.parse_args()

    outdir = f"science/output/{SLUG}"
    cache = f"science/cache/{SLUG}"
    os.makedirs(outdir, exist_ok=True)

    exps = load_exposures()
    target = SkyCoord(TARGET_RA, TARGET_DEC, unit="deg")

    # ---- epoch table + external answer key
    ep = (exps.groupby("epoch").agg(mjd_lo=("mjd", "min"), mjd_hi=("mjd", "max"),
                                    mjd_med=("mjd", "median"), date_first=("date", "min"),
                                    date_last=("date", "max")).reset_index())
    ext = parse_external(a.external, a.band) if a.external else None
    base = float(ext["mag"].median()) if ext is not None and len(ext) else None
    ep["ext_mag_median"], ep["n_ext_points"], ep["external_state"] = None, 0, "no_external_data"
    if ext is not None:
        for i, r in ep.iterrows():
            m, n = epoch_external(ext, r.mjd_lo, r.mjd_hi)
            ep.loc[i, "ext_mag_median"] = m
            ep.loc[i, "n_ext_points"] = n
            ep.loc[i, "external_state"] = label_state(m, base)
    ep.to_csv(f"{outdir}/rwaur_answer_key.csv", index=False)
    print(ep.to_string(index=False))

    # ---- SPHEREx measurements
    stars = gaia_steady_stars(target)
    print("steady Gaia comparison stars:", len(stars))
    coords = SkyCoord([target.ra.deg] + list(stars.ra.deg), [target.dec.deg] + list(stars.dec.deg), unit="deg")

    pairs = pick_pairs(exps, a.pairs)
    cache_meas = {}

    def get(idx):
        if idx not in cache_meas:
            p = download(exps.loc[idx], cache)
            cache_meas[idx] = measure_exposure(p, coords) if p else None
        return cache_meas[idx]

    rows = []
    for k, (ea, eb, ia, ib, ov) in enumerate(pairs):
        print(f"[{k + 1}/{len(pairs)}] epoch {ea}->{eb}  {exps.loc[ia, 'file']} vs {exps.loc[ib, 'file']}")
        try:
            ma, mb = get(ia), get(ib)
            res = analyse_pair(ma, mb) if ma and mb else None
        except Exception as e:
            print("   skipped:", e)
            res = None
        if res:
            res.update({"epoch_a": ea, "epoch_b": eb, "detector": int(exps.loc[ia, "detector"]),
                        "wl_a": exps.loc[ia, "wavelength_um"], "wl_b": exps.loc[ib, "wavelength_um"],
                        "overlap": ov})
            rows.append(res)
    pr = pd.DataFrame(rows)
    pr.to_csv(f"{outdir}/rwaur_pair_results.csv", index=False)

    # ---- aggregate per epoch pair and compare with external
    comp = []
    for ea, eb in EPOCH_PAIRS:
        s = pr[(pr.epoch_a == ea) & (pr.epoch_b == eb)] if len(pr) else pr
        if len(s) == 0:
            comp.append({"epoch_a": ea, "epoch_b": eb, "n_exposure_pairs": 0})
            continue
        c = classify_pair(s)
        sph = c["direction"]
        row = {"epoch_a": ea, "epoch_b": eb, "n_exposure_pairs": len(s),
               "spherex_change_pct": round(100 * c["change"], 2), "threshold_pct": round(100 * c["thr"], 2),
               "pair_to_pair_spread_pct": round(100 * c["spread"], 1),
               "mean_saturated_pixels": round(c["sat_mean"], 1), "spherex_direction": sph}
        ma_, mb_ = ep.loc[ep.epoch == ea, "ext_mag_median"].iloc[0], ep.loc[ep.epoch == eb, "ext_mag_median"].iloc[0]
        if ma_ is not None and mb_ is not None and not pd.isna(ma_) and not pd.isna(mb_):
            d = float(mb_) - float(ma_)
            row.update({"external_dmag": round(d, 3), "external_direction": direction_from_dmag(d),
                        "agrees": (direction_from_dmag(d) == sph) if sph != "inconclusive" else None})
        comp.append(row)

    done = [c for c in comp if c.get("agrees") is not None]
    k_ok = sum(bool(c["agrees"]) for c in done)
    measured = [c for c in comp if "spherex_direction" in c]
    n_incon = sum(c["spherex_direction"] == "inconclusive" for c in measured)
    if done:
        sentence = (f"Our RW Aur brightness changes agree with external monitoring in {k_ok} of "
                    f"{len(done)} reliable epoch pairs ({n_incon} of {len(measured)} pairs inconclusive; "
                    f"prototype, 3 epochs).")
    elif measured and n_incon == len(measured):
        sentence = ("RW Aur is too bright for reliable SPHEREx photometry at these epochs: repeated "
                    "measurements at the same wavelength disagree more than steady stars do, so we report "
                    "a measurement limit, not a brightness change.")
    elif measured and n_incon > 0:
        ok = [c for c in measured if c["spherex_direction"] != "inconclusive"]
        det = "; ".join(f"epoch {c['epoch_a']}->{c['epoch_b']}: {c['spherex_direction'].replace('_', ' ')} "
                        f"({c['spherex_change_pct']:+.1f}%, threshold {c['threshold_pct']:.0f}%)" for c in ok)
        sentence = (f"RW Aur is near SPHEREx's saturation limit: {n_incon} of {len(measured)} epoch pairs gave "
                    f"inconsistent repeated measurements, so we report a measurement limit, not a brightness "
                    f"change. Reliable pair(s): {det} (prototype, 3 epochs, not yet compared with external data).")
    elif measured:
        sentence = None   # need the external CSV to compare
    else:
        sentence = None
    summary = {"epoch_pair_comparison": comp, "agree": k_ok, "total_compared": len(done),
               "slide_sentence": sentence,
               "caveats": ["optical external band vs 0.75-5 um SPHEREx: only direction compared",
                           "RW Aur is a close binary (~1.5 arcsec); one 6.15 arcsec pixel blends both",
                           "only 3 epochs; epoch pairs share epochs, so they are not independent"]}
    json.dump(summary, open(f"{outdir}/rwaur_summary.json", "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))

    # ---- optional plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        if ext is not None and len(ext):
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(ext["t"], ext["mag"], ".", ms=3, alpha=0.5)
            for _, r in ep.iterrows():
                ax.axvspan(r.mjd_lo, r.mjd_hi, color="orange", alpha=0.3)
            ax.invert_yaxis(); ax.set_xlabel("MJD"); ax.set_ylabel("mag (external)")
            ax.set_title("RW Aur: external monitoring, SPHEREx epochs shaded")
            fig.tight_layout(); fig.savefig(f"{outdir}/rwaur_external_vs_epochs.png", dpi=150)
    except Exception as e:
        print("plot skipped:", e)


if __name__ == "__main__":
    main()