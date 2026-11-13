// Talks to the Flask API. If the API is unreachable (static deploy, sleeping free tier),
// falls back to the pre-baked files in /data so the five test targets always work.

import { dataUrl } from './paths.js'

const API = import.meta.env.VITE_API_BASE ?? ''
// a static-only build (GitHub Pages) has no API at all: skip the request instead of waiting for a 404
const NO_API = import.meta.env.VITE_STATIC === '1'

export class NotFound extends Error {}

function qs(params) {
  return new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
}

async function apiGet(path, params) {
  if (NO_API) throw new Error('API not available')
  const r = await fetch(`${API}${path}?${qs(params)}`)
  const ctype = r.headers.get('content-type') || ''
  if (!ctype.includes('json')) throw new Error('API not available') // e.g. static host returned index.html
  const j = await r.json()
  if (r.status === 404) throw new NotFound(j.message || 'Not found')
  if (!r.ok) throw new Error(j.message || `HTTP ${r.status}`)
  return j
}

function sepDeg(ra1, dec1, ra2, dec2) {
  const d = Math.PI / 180
  const c = Math.sin(dec1 * d) * Math.sin(dec2 * d) + Math.cos(dec1 * d) * Math.cos(dec2 * d) * Math.cos((ra1 - ra2) * d)
  return Math.acos(Math.min(1, Math.max(-1, c))) / d
}

async function staticFrames({ ra, dec, fov, target }) {
  const idx = await (await fetch(dataUrl('/data/index.json'))).json()
  let hit = target ? idx.find((t) => t.target === target) : null
  if (!hit && !target) {
    hit = idx
      .filter((t) => t.target !== 'mock')
      .map((t) => ({ ...t, sep: sepDeg(ra, dec, t.ra, t.dec) }))
      .filter((t) => t.sep <= Math.max(fov / 2, 0.05))
      .sort((a, b) => a.sep - b.sep)[0]
  }
  if (!hit) throw new NotFound('No pre-processed SPHEREx frames for this position yet. Try one of the test targets.')
  const m = await (await fetch(dataUrl(hit.manifest))).json()
  return { ...m, _via: 'static' }
}

export async function getFrames(p) {
  try {
    return { ...(await apiGet('/api/frames', p)), _via: 'api' }
  } catch (e) {
    if (e instanceof NotFound) throw e
    return staticFrames(p)
  }
}

// Static site: each target folder may hold spectrum.json (science/make_spectrum.py). It describes the
// target only, so it is shown when the click lands within NEAR_ARCSEC of where the target is on some date.
const NEAR_ARCSEC = 30

async function staticSpectrum({ ra, dec, target }) {
  if (!target) return { points: [], note: 'Spectra of positions outside our five targets need the live server.' }
  let s
  try {
    const r = await fetch(dataUrl(`/data/${target}/spectrum.json`))
    if (!r.ok || !(r.headers.get('content-type') || '').includes('json')) throw new Error('none')
    s = await r.json()
  } catch {
    return { points: [], note: 'This target\'s spectrum has not been measured yet.' }
  }
  const spots = s.positions?.length ? s.positions : [[s.ra, s.dec]]
  const near = spots.some(([a, d]) => sepDeg(ra, dec, a, d) * 3600 <= NEAR_ARCSEC)
  if (!near) return { points: [], note: `Click the target itself: measured spectra exist for ${s.label || target} only (other spots need the live server).` }
  return { ...s, _via: 'static' }
}

export async function getSpectrum(p) {
  try {
    return await apiGet('/api/spectrum', p)
  } catch {
    return staticSpectrum(p)
  }
}


export async function getSimbad(p) {
  try {
    return await apiGet('/api/simbad', p)
  } catch {
    return null
  }
}
