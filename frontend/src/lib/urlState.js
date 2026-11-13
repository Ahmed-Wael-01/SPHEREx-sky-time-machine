// The URL holds the view: ?ra=133.795&dec=-7.245&fov=0.2&det=0&mode=frames&t=0  (or ?target=wise0855)
// so any view can be shared or embedded. ra/dec also accept sexagesimal (ra=08h55m10.8s).
import { parseRA, parseDec } from './coords.js'

export function readUrl() {
  const p = new URLSearchParams(window.location.search)
  const num = (k) => (p.has(k) && p.get(k) !== '' ? Number(p.get(k)) : undefined)
  const hasTargetOrCoords = p.has('target') || p.has('ra')
  return {
    view: p.get('view') || (hasTargetOrCoords ? 'app' : 'home'),
    target: p.get('target') || undefined,
    ra: p.get('ra') ? (Number.isNaN(parseRA(p.get('ra'))) ? undefined : parseRA(p.get('ra'))) : undefined,
    dec: p.get('dec') ? (Number.isNaN(parseDec(p.get('dec'))) ? undefined : parseDec(p.get('dec'))) : undefined,
    fov: num('fov'),
    det: num('det'),
    mode: p.get('mode') || undefined,
    t: num('t'),
    embed: p.get('embed') === '1',
  }
}

export function writeUrl(state) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(state)) {
    if (v !== undefined && v !== null && v !== '' && !Number.isNaN(v)) p.set(k, String(v))
  }
  const url = `${window.location.pathname}?${p.toString()}`
  window.history.replaceState(null, '', url)
}
