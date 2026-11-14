# SPHEREx Sky Time Machine

**Team Null Point · NASA Space Apps Cairo 2026 · Challenge: "Planet X and SPHEREx"**

Type a sky position (or pick a test target) and watch NASA SPHEREx infrared images of that spot play like a short video. Anything that moves or changes brightness stands out. Difference mode shows what changed; sum mode stacks every visit into a deeper image; clicking a point shows its spectrum.

We do not claim to find Planet X. It's the motivation: the tool gives anyone the means to look.

**Live site:** https://ahmed-wael-01.github.io/SPHEREx-sky-time-machine/ (no login; five targets: WISE 0855, Barnard's Star, Epsilon Indi B, RW Aurigae, R Draconis)

## Results (real SPHEREx data, November 2026)

Every number below comes from real SPHEREx photos (IRSA, releases QR3 + DR1), checked against public catalogues. None comes from synthetic data. "Prototype" means a small sample: quote it with that word.

| What we checked | Result | How it was measured |
|---|---|---|
| Our aligned pictures vs the Gaia star catalogue | median offset **0.03″**, scatter **0.17″** (pixels are 6.15″) | Gaia DR3 stars moved to each photo's date, compared with measured positions |
| Target list vs Gaia | Barnard's Star: our predicted position is **0.006″** from Gaia DR3; Epsilon Indi B: **0.7″** from the Gaia source (G = 18.0) | catalogue position + proper motion propagated to Gaia's epoch (Anton) |
| WISE 0855, the coldest known brown dwarf | visible only at **4–5 µm** (about 10–18σ in the stacks), nothing below ~3.5 µm; moves west along its predicted path | stacks per detector; spectrum below |
| WISE 0855 spectrum vs WISE catalogue | **0.47 mJy** at 4.4–5.0 µm vs **0.43 mJy** from WISE W2 | 256 photos, one colour each; the Gaia star 8″ away fitted together with it (`make_spectrum.py`) |
| WISE 0855 brightness over time | **steady** within about 13% (3 passes) | light curve at matched colours, with a 10% allowance for the neighbour fit |
| Barnard's Star and Epsilon Indi B brightness | **steady** within about 5% and 3% (control: neither is a known variable) | same light-curve method (`make_spectrum.py`) |
| Mover finder on known movers | **14 of 14** appearances recovered (Barnard's Star 6/6, Epsilon Indi B 8/8), all within **1.2 px** (0.6–7.3″) of the prediction | 4–5 µm difference images, 5σ, 2 px match radius (Remon) |
| Mover finder, blind | **not ready**: 130–210 unvetted spots per difference image, mostly leftovers of stars that each pass sees in a slightly different colour | same run; next step: keep only spots moving steadily over ≥ 3 passes |
| R Draconis (Mira-type variable) | glow 7–10 px from the overloaded core changes about **1.6×** between the 3 well-measured passes (1.6–2.4 µm, May 2025 → Apr 2026); up to 4× if two passes measured on only 1–2 photos are included | `make_spectrum.py` glow photometry, same ring on every photo; verdict counts passes with ≥ 3 photos |
| RW Aurigae | Sep 2025 → Feb/Mar 2026: **no significant change** (+5.2%, threshold 13%); the other two pairs **inconclusive**: RW Aur is at SPHEREx's overload limit (overloaded in 302 of 323 photos) | same colour on both dates, calibrated by steady Gaia stars (Fatma); the site's light curve agrees: inconclusive |
| Variable-star flagger (prototype) | **3 of 8** known variables caught, **3 false alarms** in 20 steady stars | held-out Gaia-labelled stars in the RW Aur field (Fatma) |
| Reading only the pixels we need (NASA's Amazon S3 copy) | pixels **identical** to IRSA cutouts in 5 of 5 photos; star-shape table identical a year apart; speed about the same as cutouts at our 0.5° view | `science/test_partial_read.py` |

What these numbers do **not** show: no new movers or variables were found or claimed. The tool recovers known objects; finding new ones needs the blind-search clean-up above and the any-position mode below.

**Next steps:** a "search any position" button (the pipeline already takes any RA/Dec, in minutes per position; a live version needs a server next to NASA's cloud copy), wider fields from the same copy, the blind mover search, and comparison of RW Aur with outside monitoring once it covers our dates.

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

# 1. Bake frames for a target (talks to NASA/IPAC IRSA; first run downloads ~1.75 GB per target at the default 0.5° field)
python science/fetch_cutouts.py --target wise0855
python science/fetch_cutouts.py --target wise0855 --max-exposures 40   # quick first test
python science/fetch_cutouts.py --all                                  # all five test targets
python science/fetch_cutouts.py --ra 133.795 --dec -7.245 --slug mypatch --size 0.5

# 2. API
cd backend && python app.py           # http://localhost:5000/api/health
python -m pytest -q                    # backend tests (from backend/)

# 3. Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

**Everything the public sees is real SPHEREx data.** For developers only, `python science/make_synthetic.py` writes fake SPHEREx-shaped cutouts so code can be smoke-tested offline; they play at `/?target=mock` (not linked anywhere in the app, labelled as synthetic). They are never used for accuracy numbers: detection and variability are trained and tested on real stars and real asteroids with catalogue labels.

**Viewer options:** colour maps (heat, viridis, inferno, Null Point blue; blue–red for difference mode), contrast, and a **3-colour infrared** view on "All" (blue 0.75–1.6, green 1.6–3.8, red 3.8–5 µm; cold brown dwarfs show red). Overlays: target ring, its path over time, RA/Dec grid, scale bar, and **Gaia DR3** (moved to each frame's date with proper motion) and **AllWISE** sources. Hover shows RA/Dec. Hatched areas = no data.

Catalogues come from `python science/fetch_catalogs.py --target <slug>` (run automatically after each online bake; writes `catalogs.json` next to the manifest).

**Spectrum and light curve:** click on a target to see its brightness at every colour (one point per photo), and open "Details" for the light curve with a verdict ("steady" or "changes beyond the uncertainty"). Made by `python science/make_spectrum.py --target <slug>` from the downloaded photos. **Mover finder** overlay: what the automatic finder detected on each date (`detections.json`).

Shareable views: `/viewer/target=wise0855`, `/viewer?ra=133.795&dec=-7.245&fov=0.2&det=6&mode=diff`, `/viewer?ra=08h55m10.8s&dec=-07:14:42.5` (older `/?target=…` links still work). Add `&embed=1` for a bare player to embed elsewhere.

## Deploy

**Website (GitHub Pages, free):** repo Settings → Pages → Source: **GitHub Actions**. Every push to `main` then builds and publishes `https://<user>.github.io/SPHEREx-sky-time-machine/` (`.github/workflows/pages.yml`). It is static only: frames, overlays, close-up, spectra and mover-finder results all work from the files in `public/data`; only the SIMBAD object lookup needs the API, and says so.

**Website (Vercel, free, alternative):** vercel.com → Add New → Project → import this repo → Root Directory `frontend` (framework: Vite) → Deploy. It works on its own: with no API it reads the baked files in `public/data`.

**API (Render, free):** render.com → New → Blueprint → this repo (uses `render.yaml`). When it's live, add `VITE_API_BASE=https://<your-service>.onrender.com` in Vercel → Settings → Environment Variables and redeploy. Free Render services sleep after inactivity; the site keeps working from static files while it wakes.

New frames: run the pipeline, commit `frontend/public/data/`, push. The site redeploys automatically.

Pictures vs. science data: in the website pictures, overloaded star cores are drawn white and small isolated holes (≤ 40 px, pixels flagged in the only photo of that spot) are painted with their surroundings. `stacks.fits` keeps all of these blank, and every measurement uses `stacks.fits`.

## How the pipeline works (`science/fetch_cutouts.py`)

1. **Position.** Catalogue position and proper motion from `science/targets.json` (SIMBAD as a fallback for other names), moved to the cutout epoch (`--epoch`, default 2026.0).
2. **Query.** IRSA TAP on `spherex.artifact JOIN spherex.plane`: every Spectral Image whose footprint contains the position, all detectors, all releases in the TAP tables (QR3 + DR1 as of Nov 2026; IRSA says they supersede QR2). Duplicates across releases are dropped.
3. **Cutouts.** IRSA cutout service (`?center=ra,decd&size=deg`), cached in `science/cache/<slug>/`, parallel downloads with retries.
4. **Clean.** `IMAGE − ZODI` (ZODI is not pre-subtracted). Bad pixels are masked **by flag name**, read from the `MSKNnnnn` cards in the FLAGS header. OVERFLOW, NONLINEAR and SOURCE are left unmasked on purpose: masking them would cut holes in bright stars (Barnard's Star). They're still counted in the flag summary.
5. **Align.** `reproject` every cutout onto one north-up TAN grid at 6.15″/px centred on the target.
6. **Stack.** Split exposures into survey passes by a 60-day gap (passes longer than 90 days are cut into ~60-day pieces), then do an inverse-variance mean per (pass, detector) and per pass over all six detectors.
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
- Gaia DR3 (ESA) and AllWISE (NASA/IPAC) catalogues for overlays and checks; ASAS-SN Sky Patrol for the RW Aur outside light curve
- Astropy, astroquery, reproject, photutils, NumPy, Flask, React, Vite

## AI use disclosure

We used Claude (Anthropic), an AI assistant, throughout the project, and we want to be specific about where:

- **Planning and writing:** project plan, task breakdown, proposal text, market research, slide text, and this README.
- **Code written with Claude:** most of the data pipeline (`science/fetch_cutouts.py`, `fetch_catalogs.py`, `make_spectrum.py`, `fill_png_holes.py`, `test_partial_read.py`, `photometry_quickstart.py`), the Flask API, large parts of the React viewer (player, overlays, close-up, colour maps, spectrum and mover-finder display), and the GitHub Pages deployment.
- **Reviews:** Claude reviewed teammates' branches before merging and found bugs (for example a `.gitignore` rule that would have hidden the website's data folder, and a light-curve method that created fake variability).

What the team did: came up with the idea and approach (the five test targets were suggested by the challenge), designed the logo, downloaded and processed all the real SPHEREx data on our own machines, ran every measurement and checked the outputs, designed the home page and interface (Youssef), built the mover finder (Remon), the variable-star module (Fatma), the photometry checks (Alaa) and the Gaia validation (Anton), and decided what to claim. Every result in the table above was produced by running the code on real data and checked by a person.
