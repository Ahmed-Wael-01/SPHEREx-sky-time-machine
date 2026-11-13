// Gnomonic (TAN) projection matching the pipeline's north-up grid.
// Image fractions: fx 0..1 left→right (east is left), fy 0..1 top→bottom (north is up).

const D = Math.PI / 180

export function makeWcs(manifest) {
  const ra0 = manifest.ra * D
  const dec0 = manifest.dec * D
  const span = (manifest.pixels * manifest.pixel_scale_arcsec) / 3600 // degrees across the image

  function toFrac(ra, dec) {
    const a = ra * D
    const d = dec * D
    const cosc = Math.sin(dec0) * Math.sin(d) + Math.cos(dec0) * Math.cos(d) * Math.cos(a - ra0)
    if (cosc <= 0) return null
    const xi = (Math.cos(d) * Math.sin(a - ra0)) / cosc / D
    const eta = (Math.cos(dec0) * Math.sin(d) - Math.sin(dec0) * Math.cos(d) * Math.cos(a - ra0)) / cosc / D
    return { fx: 0.5 - xi / span, fy: 0.5 - eta / span }
  }

  function toSky(fx, fy) {
    const xi = (0.5 - fx) * span * D
    const eta = (0.5 - fy) * span * D
    const rho = Math.hypot(xi, eta)
    const c = Math.atan(rho)
    if (rho === 0) return { ra: manifest.ra, dec: manifest.dec }
    const dec = Math.asin(Math.cos(c) * Math.sin(dec0) + (eta * Math.sin(c) * Math.cos(dec0)) / rho)
    const ra = ra0 + Math.atan2(xi * Math.sin(c), rho * Math.cos(dec0) * Math.cos(c) - eta * Math.sin(dec0) * Math.sin(c))
    return { ra: ((ra / D) % 360 + 360) % 360, dec: dec / D }
  }

  return { toFrac, toSky, span }
}

// Proper motion from the catalogue epoch to a decimal year (linear; fine over decades for a small field).
export function propagate(ra, dec, pmra, pmdec, fromYear, toYear) {
  const dt = toYear - fromYear
  return {
    ra: ra + (pmra * dt) / 3.6e6 / Math.max(Math.cos(dec * D), 1e-6),
    dec: dec + (pmdec * dt) / 3.6e6,
  }
}

export const mjdToYear = (mjd) => 2000 + (mjd - 51544.5) / 365.25

// Round step (degrees) so the image gets ~3–6 grid lines.
const STEPS = [5 / 3600, 10 / 3600, 15 / 3600, 30 / 3600, 1 / 60, 2 / 60, 5 / 60, 10 / 60, 15 / 60, 0.5, 1, 2]
export function gridStep(spanDeg) {
  return STEPS.find((s) => spanDeg / s <= 6) ?? 5
}

// Grid polylines in image fractions: lines of constant Dec and of constant RA.
export function gridLines(wcs, manifest, scale = 1) {
  const step = gridStep(wcs.span / scale)
  // RA lines on round steps of time (1 s of time = 1/240 deg)
  const raSpan = wcs.span / scale / Math.max(Math.cos(manifest.dec * D), 0.05)
  const TIME = [1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600]
  const raStep = (TIME.find((t) => raSpan / (t / 240) <= 6) ?? 7200) / 240
  const half = wcs.span * 0.75
  const lines = []
  const decLo = Math.floor((manifest.dec - half) / step) * step
  for (let j = 0; decLo + j * step <= manifest.dec + half; j++) {
    const dec = decLo + j * step
    const pts = []
    for (let i = 0; i <= 40; i++) {
      const ra = manifest.ra - half / Math.cos(manifest.dec * D) + (i / 40) * 2 * half / Math.cos(manifest.dec * D)
      const p = wcs.toFrac(ra, dec)
      if (p) pts.push(p)
    }
    lines.push({ kind: 'dec', value: dec, pts })
  }
  const raHalf = half / Math.max(Math.cos(manifest.dec * D), 0.05)
  const raLo = Math.floor((manifest.ra - raHalf) / raStep) * raStep
  for (let j = 0; raLo + j * raStep <= manifest.ra + raHalf; j++) {
    const ra = raLo + j * raStep
    const pts = []
    for (let i = 0; i <= 40; i++) {
      const dec = manifest.dec - half + (i / 40) * 2 * half
      const p = wcs.toFrac(ra, dec)
      if (p) pts.push(p)
    }
    lines.push({ kind: 'ra', value: ((ra % 360) + 360) % 360, pts })
  }
  return { step, raStep, lines }
}
