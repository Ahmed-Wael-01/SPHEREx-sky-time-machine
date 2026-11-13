// Where the site lives. On Vercel or locally that is "/"; on GitHub Pages it is the repo's sub-folder
// ("/SPHEREx-sky-time-machine/"), set at build time with VITE_BASE. Every link and data file goes
// through these helpers so the same code works in both places.
export const BASE = import.meta.env.BASE_URL || '/'

// "/data/wise0855/x.png" -> "/SPHEREx-sky-time-machine/data/wise0855/x.png" on GitHub Pages
export function dataUrl(u) {
  if (typeof u !== 'string' || !u.startsWith('/data/') || BASE === '/') return u
  return BASE + u.slice(1)
}

// Page path inside the site, without the base: "/SPHEREx-sky-time-machine/viewer/..." -> "/viewer/..."
export function sitePath(pathname) {
  const b = BASE.replace(/\/$/, '')
  return b && pathname.startsWith(b) ? pathname.slice(b.length) || '/' : pathname
}

// The other way round: "/viewer/..." -> "/SPHEREx-sky-time-machine/viewer/..."
export function fullPath(p) {
  return BASE.replace(/\/$/, '') + p
}
