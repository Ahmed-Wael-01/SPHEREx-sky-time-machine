// URL State Routing for SPHEREx Sky Time Machine
// Home page: /
// Sky Time Machine viewer page: /viewer/target=<slug> (or /viewer?target=<slug>)
import { parseRA, parseDec } from './coords.js'

export function readUrl() {
  const pathname = window.location.pathname.replace(/\/+$/, '') // strip trailing slashes
  const p = new URLSearchParams(window.location.search)
  const num = (k) => (p.has(k) && p.get(k) !== '' ? Number(p.get(k)) : undefined)

  // 1. Extract target from path: /viewer/target=wise0855 or /viewer/wise0855 (also supports legacy /skytimemachine)
  let pathTarget
  const pathMatch = pathname.match(/^\/(?:viewer|skytimemachine)(?:\/target=|\/)([^/?#]+)/i)
  if (pathMatch) {
    pathTarget = decodeURIComponent(pathMatch[1])
  }

  const target = pathTarget || p.get('target') || undefined
  const isViewerPath = pathname.startsWith('/viewer') || pathname.startsWith('/skytimemachine')

  // Determine view:
  // If on /viewer* or explicitly ?view=app: view is 'app'.
  // Otherwise if path is '/' (root), view is strictly 'home' (clean landing page).
  let view = 'home'
  if (isViewerPath || p.get('view') === 'app') {
    view = 'app'
  } else if (pathname === '' || pathname === '/') {
    view = 'home'
  } else if (target || p.has('ra')) {
    view = 'app'
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
  // When on Home page, the URL must be strictly "/" with NO query params
  if (state.view === 'home') {
    const targetUrl = state.embed ? '/?embed=1' : '/'
    if (window.location.pathname + window.location.search !== targetUrl) {
      window.history.replaceState(null, '', targetUrl)
    }
    return
  }

  // When on Sky Time Machine, write /viewer/target=<slug>
  let basePath = '/viewer'
  if (state.target) {
    basePath = `/viewer/target=${encodeURIComponent(state.target)}`
  }

  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(state)) {
    if (v === undefined || v === null || v === '' || Number.isNaN(v)) continue
    // Skip 'view'
    if (k === 'view') continue
    // If target is in the path, omit from query params
    if (k === 'target' && basePath.includes('/target=')) continue
    p.set(k, String(v))
  }

  const queryString = p.toString()
  const targetUrl = queryString ? `${basePath}?${queryString}` : basePath

  if (window.location.pathname + window.location.search !== targetUrl) {
    window.history.replaceState(null, '', targetUrl)
  }
}
