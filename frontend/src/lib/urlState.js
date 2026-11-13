// URL State Routing for SPHEREx Sky Time Machine
// Home page: /
// Sky Time Machine page: /skytimemachine/target=<slug> (or /skytimemachine?target=<slug>)
import { parseRA, parseDec } from './coords.js'

export function readUrl() {
  const pathname = window.location.pathname.replace(/\/+$/, '') // strip trailing slashes
  const p = new URLSearchParams(window.location.search)
  const num = (k) => (p.has(k) && p.get(k) !== '' ? Number(p.get(k)) : undefined)

  // 1. Extract target from path: /skytimemachine/target=wise0855 or /skytimemachine/wise0855
  let pathTarget
  const pathMatch = pathname.match(/^\/skytimemachine(?:\/target=|\/)([^/?#]+)/i)
  if (pathMatch) {
    pathTarget = decodeURIComponent(pathMatch[1])
  }

  const target = p.get('target') || pathTarget || undefined
  const hasTargetOrCoords = Boolean(target || p.has('ra'))
  const isSkyTimeMachinePath = pathname.startsWith('/skytimemachine')

  // Determine view:
  // If explicitly on /skytimemachine* or has target/coords, view is 'app'.
  // Otherwise if path is '/' (root) and no target/coords, view is 'home'.
  let view = 'home'
  if (isSkyTimeMachinePath || hasTargetOrCoords || p.get('view') === 'app') {
    view = 'app'
  } else if (p.get('view') === 'home' || pathname === '' || pathname === '/') {
    view = 'home'
  }

  return {
    view,
    target,
    ra: p.get('ra') ? (Number.isNaN(parseRA(p.get('ra'))) ? undefined : parseRA(p.get('ra'))) : undefined,
    dec: p.get('dec') ? (Number.isNaN(parseDec(p.get('dec'))) ? undefined : parseDec(p.get('dec'))) : undefined,
    fov: num('fov'),
    det: p.get('det') === 'long' ? 'long' : num('det'),
    mode: p.get('mode') || undefined,
    t: num('t'),
    embed: p.get('embed') === '1',
  }
}

export function writeUrl(state) {
  const p = new URLSearchParams()
  let basePath = '/'

  if (state.view === 'app') {
    if (state.target) {
      basePath = `/skytimemachine/target=${encodeURIComponent(state.target)}`
    } else {
      basePath = '/skytimemachine'
    }
  } else {
    basePath = '/'
  }

  for (const [k, v] of Object.entries(state)) {
    if (v === undefined || v === null || v === '' || Number.isNaN(v)) continue
    // Skip 'view' because the path represents the view (/ vs /skytimemachine)
    if (k === 'view') continue
    // If target is in the path, omit from query params
    if (k === 'target' && state.view === 'app' && basePath.includes('/target=')) continue
    p.set(k, String(v))
  }

  const queryString = p.toString()
  const targetUrl = queryString ? `${basePath}?${queryString}` : basePath

  if (window.location.pathname + window.location.search !== targetUrl) {
    window.history.replaceState(null, '', targetUrl)
  }
}
