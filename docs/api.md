# API contract

Base URL: same origin in dev (Vite proxies `/api` to Flask on :5000). Set `VITE_API_BASE` in the frontend when the API lives elsewhere.

Every response carries `"source"`: `"prebaked"` (real pipeline output), or `"mock"` (placeholder). The frontend shows a banner for mock data.

Position parameters are decimal degrees. `target=<slug>` can replace `ra`/`dec`. Errors: `400 {"error":"bad_request","message":…}`, `404 {"error":"not_baked","message":…,"targets":[…]}`.

## `GET /api/frames?ra=&dec=&fov=[&target=]`

Exactly the `manifest.json` that `science/fetch_cutouts.py` writes to `frontend/public/data/<slug>/`.

```json
{
  "target": "wise0855", "name": "WISE J085510.83-071442.5",
  "ra": 133.7943, "dec": -7.2431, "fov": 0.2, "pixels": 119, "pixel_scale_arcsec": 6.15,
  "orientation": "north up, east left",
  "pm_mas_yr": [-8123, 673], "n_exposures": 412, "n_epochs": 3, "detectors": [1,2,3,4,5,6],
  "detector_wavelength_um": {"0": [0.75, 5.0], "1": [0.75, 1.1], "...": "..."},
  "masked_flags": ["TRANSIENT", "..."], "source": "prebaked", "generated": "2026-11-13T12:00:00Z",
  "visits": [
    {"date": "2025-05-05", "mjd": 60800.3, "epoch": 0, "detector": 0,
     "wavelength_um": [0.75, 5.0],
     "image_url": "/data/wise0855/2025-05-05_all.png",
     "diff_url": "/data/wise0855/2025-05-05_all_diff.png",
     "diff_sigma_mjysr": 0.023, "n_exposures": 18,
     "flags": {"TRANSIENT": 108, "OVERFLOW": 0, "HOT": 72, "...": 0},
     "predicted": {"ra": 133.7964, "dec": -7.2505, "fx": 0.49, "fy": 0.53}}
  ],
  "deep": [{"detector": 0, "image_url": "/data/wise0855/deep_all.png", "n_exposures": 72, "wavelength_um": [0.75, 5.0]}]
}
```

- `detector: 0` = all six detectors stacked together; 1–6 = one detector each.
- `epoch` = one survey pass (exposures closer than `--gap-days`, default 20).
- `diff_url` = this pass minus the stack of all *other* passes, scaled ±5σ (mid-grey = no change, white = brighter now, black = fainter now).
- `predicted.fx/fy` = target position from proper motion on that date, as a fraction of the image (0,0 = top-left).
- `flags` = pixel counts per flag summed over the stacked cutouts (full cutout area).
- Also in the same folder: `exposures.json` (one row per exposure: mjd, detector, wavelength at target, pixel position in the cutout, cached file name) for photometry.

## `GET /api/spectrum?ra=&dec=[&target=]`

Serves `frontend/public/data/<slug>/spectrum.json` if it exists (Alaa's photometry output), else mock.

```json
{"ra": 133.795, "dec": -7.245, "name": "wise0855", "source": "prebaked",
 "points": [{"wavelength_um": 4.62, "flux_mjy": 0.41, "err_mjy": 0.06, "date": "2025-05-03", "detector": 6, "flagged": false}],
 "light_curve": [{"date": "2025-05-05", "mjd": 60800.3, "flux_mjy": 0.41, "err_mjy": 0.03, "detector": 0}]}
```

## `GET /api/detections?ra=&dec=&fov=[&target=]`

Serves `frontend/public/data/<slug>/detections.json` if it exists (Remon / Fatma), else mock.

```json
{"ra": 133.795, "dec": -7.245, "fov": 0.2, "source": "prebaked",
 "candidates": [{"ra": 133.7964, "dec": -7.2505, "fx": 0.49, "fy": 0.53, "score": 0.93,
                 "kind": "mover", "known_match": "WISE 0855", "pm_mas_yr": [-8123, 673]}],
 "variability": [{"ra": 76.956, "dec": 30.401, "score": 0.88, "known_match": "RW Aur"}]}
```

## Other

- `GET /api/health` – ok, data dir, baked targets, cache backend (`memory` or `redis`).
- `GET /api/targets` – contents of `frontend/public/data/index.json`.
- `GET /data/<path>` – the baked PNG/JSON files.
