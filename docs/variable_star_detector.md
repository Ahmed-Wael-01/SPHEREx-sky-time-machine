# Variable-star flagging and the RW Aurigae check

Owner: Fatma Amr. Scripts: `science/variability.py`, `science/rwaur_answer_key.py`, `science/fetch_asassn.py`, `science/gaia_utils.py`. Checker: `science/tests/check_rwaur_deliverables.py`.

Status: **prototype**. Real SPHEREx data only, 3 epochs of RW Aur, small test samples. Every number below should be quoted with that caveat.

## 1. What this part does

1. **Variable-star flagging.** Measure many Gaia stars in the same SPHEREx exposures, compare each star only to itself at matched wavelength on different days, tune a threshold on steady stars, test on stars held back.
2. **RW Aurigae check.** Measure RW Aur (a known, strongly variable young star) in each SPHEREx epoch and compare epoch-to-epoch changes with external monitoring (AAVSO / ASAS-SN) when such data covers our dates.

## 2. What makes this approach different

- **Self-calibrating.** Brightness is never compared across different wavelengths or against a model. A star is compared to itself, in the same wavelength bin, calibrated by steady stars in the same two exposures.
- **The threshold comes from steady stars, not from formal errors.** Our first notebook used only formal errors and produced chi-square = 4794 for 2 degrees of freedom. That is a calibration problem, not a discovery, so we replaced it with measured star-to-star scatter.
- **A third answer: "inconclusive".** If repeated measurements at the same wavelength disagree by more than steady stars do, or the aperture is saturated, the result is reported as a measurement limit instead of a brightness change.
- **Real labels, held-out testing.** Labels come from Gaia DR3 (`phot_variable_flag`). Tuning and testing use different stars. No synthetic data is used for any accuracy number.
- **Reproducible.** One script per task, cutouts cached in `science/cache/`, outputs in `science/output/<slug>/`, a checker that validates all deliverables.

## 3. Challenges and how we handled them

| # | Challenge | What we did |
|---|---|---|
| 1 | **The wavelength depends on where a source falls on the detector** (SPHEREx uses a linear variable filter). Early measurements of the same star looked inconsistent because they sampled different wavelengths. | Only compare exposures whose passbands overlap by at least 50% (stars are binned in 2%-wide log-wavelength bins; epoch pairs are matched on the target wavelength). Wavelength comes from the spectral WCS (`key="W"`), per star. |
| 2 | **Wrong dates.** The FITS header `DATE` is not a reliable observation time. | Use the exposure time (`mjd`) from `exposures.json` / IRSA `t_min`. Epochs: Sep 2025, Feb-Mar 2026, Sep 2026. |
| 3 | **Formal errors are far too small.** They gave chi-square = 4794 (2 dof), which is not believable. | Calibrate on an ensemble of steady Gaia stars measured in the same two exposures. The detection threshold is the 95th percentile of steady-star scatter in the tuning half. |
| 4 | **Saturation.** RW Aur is bright; some aperture pixels are flagged OVERFLOW / NONLINEAR. | Following the pipeline policy, those flags are not masked (masking would cut holes in bright stars) but they are counted per exposure. Epoch pairs with high saturation, or with large pair-to-pair disagreement, are classified `inconclusive`. |
| 5 | **Measurements disagree even at the same wavelength.** Within one epoch pair, nearly identical wavelengths gave ratios from 0.9 to 2.1, while steady stars repeat to about 2-6%. | Added the pair-to-pair spread test (`classify_pair`). 2 of 3 RW Aur epoch pairs fail it and are reported as a measurement limit. |
| 6 | **RW Aur is a close binary (~1.5 arcsec); one SPHEREx pixel is 6.15 arcsec.** | Documented as a caveat. Both components are blended in every measurement. |
| 7 | **Few epochs.** Only 3 epochs, so epoch pairs are not independent. | Reported as "3 epochs, small sample". Pair 0-2 is a consistency check, not independent evidence. |
| 8 | **External data does not cover our dates.** The ASAS-SN light curve we could download ends in Feb 2025 (MJD 60693); our first epoch is Sep 2025 (MJD 60919). AAVSO delivers data by email. | Keep the comparison code ready (`--external <csv>`). Until a CSV covering our epochs exists, we report only context from literature: AAVSO Observing Campaign #884 and Lisse et al. (2025) describe a major dimming of RW Aur starting in early 2025. No per-epoch bright/faint label is claimed. |
| 9 | **VizieR returned HTTP 404** while building the star list. | `gaia_utils.gaia_cone()` tries several Gaia sources in order (VizieR mirror, ESA Gaia archive, IRSA, VizieR CDS). In practice the ESA archive answered. |
| 10 | **Small variable sample.** Only a handful of Gaia-flagged variables fall in the field. | Report held-out numbers with the sample size and the label "tiny sample, prototype". A larger `--radius` can add more stars. |
| 11 | **Engineering issues.** Pandas 3 returns read-only arrays (shuffle failed); the data folder is `rw-aur` but an early run used `rwaur`; astropy printed long SIP warnings; full-image downloads were slow. | `.copy()` before shuffling; always run with `--slug rw-aur`; astropy log level set to WARNING (the SIP message is informational); cutouts cached in `science/cache/`. `science/cache/`, `science/output/` and `data/` are git-ignored. |

## 4. Results so far (prototype)

**RW Aur, SPHEREx only** (wavelength-matched, calibrated on steady stars):

| Epoch pair | Change | Pair-to-pair spread | Result |
|---|---|---|---|
| 0 -> 1 (Sep 2025 -> Feb/Mar 2026) | +5.2% (threshold 12.9%) | 3.3% | no significant change |
| 1 -> 2 (Feb/Mar 2026 -> Sep 2026) | -23.7% | 30.1% | inconclusive |
| 0 -> 2 | +90.7% | 87.8% | inconclusive |

Slide sentence: *RW Aur is near SPHEREx's saturation limit: 2 of 3 epoch pairs gave inconsistent repeated measurements, so we report a measurement limit, not a brightness change. Reliable pair(s): epoch 0->1: no change (+5.2%, threshold 13%) (prototype, 3 epochs, not yet compared with external data).*

**Variable-star flagging, held-out Gaia-labelled stars in the RW Aur field:** 3 of 8 known variables caught, 3 false alarms among 20 steady stars. The false-alarm rate (15%) is above the 5% design target because the tuning sample is small.

**Not yet done:** agreement with external monitoring ("X of Y epoch pairs"). It needs an external light curve covering Sep 2025 - Sep 2026.

## 5. How to run it

From the repository root (activate `.venv` first):

```bash
pip install -r requirements.txt

# 1. Variable-star flagging (writes variability_*.json/csv and a "variability" section in detections.json)
python science/variability.py --ra 76.956 --dec 30.401 --slug rw-aur --radius 0.4 --max-obs 15

# 2. RW Aur epoch comparison (SPHEREx side only)
python science/rwaur_answer_key.py

# 3. Optional: external light curve, then compare
pip install skypatrol
python science/fetch_asassn.py                      # writes data/rwaur_external.csv
python science/rwaur_answer_key.py --external data/rwaur_external.csv --band g
#   (AAVSO CSV: use --band V)

# 4. Check all deliverables
python science/tests/check_rwaur_deliverables.py
```

Outputs are written to `science/output/rw-aur/`:

| File | Content |
|---|---|
| `variable_truth.csv` | answer key: Gaia stars labelled variable / steady |
| `variability_results.csv` | per star: relative scatter, flag, tune/held-out split |
| `variability_summary.json` | threshold, variables caught, false alarms |
| `rwaur_answer_key.csv` | per epoch: external magnitude and bright/faint label (when external data exists) |
| `rwaur_pair_results.csv` | every exposure pair measured |
| `rwaur_summary.json` | epoch-pair comparison and the slide sentence |

`variability.py` also merges a `variability` section into `frontend/public/data/rw-aur/detections.json`. The file is not committed by default; agree with the detection owner before adding it.

## 6. Known limits and next steps

- 3 epochs and a small sample of known variables: numbers are prototype-level.
- `variability.py` still downloads full SPHEREx images through IRSA. Reading the small cutouts listed in `exposures.json` (as `rwaur_answer_key.py` does) would make it much faster.
- External comparison needs a light curve covering our epochs (AAVSO data by email, or another monitoring source).
- The ensemble uses steady Gaia stars (`phot_variable_flag` not VARIABLE); some are probably low-level variables, which makes the threshold conservative in the wrong direction. A cleaner steady-star list (for example, cross-matched with VSX) would help.
- Optical external bands (V, g) vs 0.75-5 um SPHEREx: only the direction of change can be compared, never the amplitude.