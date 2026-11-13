# SPHEREx Sky Time Machine

**Team Null Point · NASA Space Apps Cairo 2026 · Challenge: "Planet X and SPHEREx"**

Type a sky position (or pick a test target) and watch NASA SPHEREx infrared images of that spot play like a short video. Anything that moves or changes brightness stands out. Difference mode shows what changed; sum mode stacks every visit into a deeper image; clicking a point shows its spectrum.

We do not claim to find Planet X. It's the motivation: the tool gives anyone the means to look.

## Repo layout

```
backend/     Flask API (app.py), cache wrapper (Redis or in-memory), mock payloads, tests
frontend/    React + Vite app: player, coordinate input, FoV, difference/sum, URL state
  public/data/<target>/   baked PNG frames + manifest.json + exposures.json (served statically)
science/     data pipeline: fetch_cutouts.py, targets.json, make_synthetic.py
docs/        api.md (API contract)
```

## Quick start

```bash
# Python (3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Bake frames for a target (talks to NASA/IPAC IRSA; first run downloads cutouts)
python science/fetch_cutouts.py --target wise0855
python science/fetch_cutouts.py --target wise0855 --max-exposures 40   # quick first test
python science/fetch_cutouts.py --all                                  # all five test targets
python science/fetch_cutouts.py --ra 133.795 --dec -7.245 --slug mypatch --size 0.2

# 2. API
cd backend && python app.py            # http://localhost:5000/api/health
python -m pytest -q                    # backend tests

# 3. Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

**Everything the public sees is real SPHEREx data.** For developers only, `python science/make_synthetic.py` writes fake SPHEREx-shaped cutouts so code can be smoke-tested offline; they play at `/?target=mock` (not linked anywhere in the app, labelled as synthetic). They are never used for accuracy numbers: detection and variability are trained and tested on real stars and real asteroids with catalogue labels.

Shareable views: `/?target=wise0855`, `/?ra=133.795&dec=-7.245&fov=0.2&det=6&mode=diff`, `/?ra=08h55m10.8s&dec=-07:14:42.5`. Add `&embed=1` for a bare player to embed elsewhere.

## Deploy

**Website (Vercel, free):** vercel.com → Add New → Project → import this repo → Root Directory `frontend` (framework: Vite) → Deploy. It works on its own: with no API it reads the baked files in `public/data`.

**API (Render, free):** render.com → New → Blueprint → this repo (uses `render.yaml`). When it's live, add `VITE_API_BASE=https://<your-service>.onrender.com` in Vercel → Settings → Environment Variables and redeploy. Free Render services sleep after inactivity; the site keeps working from static files while it wakes.

New frames: run the pipeline, commit `frontend/public/data/`, push. Both services redeploy automatically.

## How the pipeline works (`science/fetch_cutouts.py`)

1. **Position.** Resolve the name with SIMBAD, then apply proper motion to the cutout epoch (`--epoch`, default 2026.0).
2. **Query.** IRSA TAP on `spherex.artifact JOIN spherex.plane`: every Spectral Image whose footprint contains the position, all detectors, all releases in the TAP tables (QR3 + DR1 as of Nov 2026; IRSA says they supersede QR2). Duplicates across releases are dropped.
3. **Cutouts.** IRSA cutout service (`?center=ra,decd&size=deg`), cached in `science/cache/<slug>/`, parallel downloads with retries.
4. **Clean.** `IMAGE − ZODI` (ZODI is not pre-subtracted). Bad pixels are masked **by flag name**, read from the `MSKNnnnn` cards in the FLAGS header. OVERFLOW, NONLINEAR and SOURCE are left unmasked on purpose: masking them would cut holes in bright stars (Barnard's Star). They're still counted in the flag summary.
5. **Align.** `reproject` every cutout onto one north-up TAN grid at 6.15″/px centred on the target.
6. **Stack.** Split exposures into survey passes by time gap, then do an inverse-variance mean per (pass, detector) and per pass over all six detectors.
7. **Difference.** Each pass minus the stack of all other passes, scaled ±5σ.
8. **Write.** PNGs, `manifest.json`, `exposures.json` → `frontend/public/data/<slug>/`; float stacks → `science/output/<slug>/stacks.fits`.

The same asinh stretch is used for every pass of a detector, so brightness changes between frames are real.

## Team workflow

- One branch per feature (`feat/player-controls`, `feat/photometry` …); someone else looks before merging to `main`.
- Raw cutouts (`science/cache/`) and float stacks (`science/output/`) are git-ignored. Baked PNGs + JSON under `frontend/public/data/` **are** committed, so the demo works without the archive.
- New science outputs plug into the API by dropping a file next to the manifest: `spectrum.json`, `detections.json` (see `docs/api.md`).

| Member | Owns |
| --- | --- |
| Ahmed Wael (lead) | Backend, pipeline, Redis, deployment, submission |
| Youssef Magdy | UI design and React frontend |
| Remon Nady | Moving-object detection on difference images |
| Fatma Amr | Variable-star flagging; models into the API |
| Alaa Ahmed | Photometry, spectra, light curves, charts |
| Anton Elia | Validation vs Gaia/WISE, injection tests |

## Data and credits

- SPHEREx data: NASA/IPAC Infrared Science Archive (IRSA). https://irsa.ipac.caltech.edu/Missions/spherex.html
- IRSA SPHEREx tutorials (query and cutout recipe): https://caltech-ipac.github.io/irsa-tutorials/
- SIMBAD (CDS Strasbourg) for name resolution and proper motions
- Astropy, astroquery, reproject, photutils, NumPy, Flask, React, Vite

**AI use disclosure:** Claude (Anthropic) helped with planning, the proposal text, the logo, the slides, and the initial code scaffold (pipeline, API and player). The team reviewed, tested and extended it.
