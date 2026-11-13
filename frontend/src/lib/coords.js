// Parse RA/Dec typed as degrees ("133.795") or sexagesimal ("08h55m10.8s", "08:55:10.8", "08 55 10.8").
// RA sexagesimal is hours; Dec sexagesimal is degrees.

function sexToNumber(str) {
  const parts = str.trim().replace(/[hdms°'"′″:]/gi, ' ').trim().split(/\s+/).map(Number)
  if (parts.some(Number.isNaN) || parts.length === 0 || parts.length > 3) return NaN
  const neg = str.trim().startsWith('-')
  const [a, b = 0, c = 0] = parts.map(Math.abs)
  const v = a + b / 60 + c / 3600
  return neg ? -v : v
}

const isSex = (s) => /[hdms°'"′″:]|\d\s+\d/i.test(s.trim())

export function parseRA(s) {
  if (s == null || String(s).trim() === '') return NaN
  s = String(s)
  const v = isSex(s) ? sexToNumber(s) * 15 : Number(s)
  return v >= 0 && v < 360 ? v : NaN
}

export function parseDec(s) {
  if (s == null || String(s).trim() === '') return NaN
  s = String(s)
  const v = isSex(s) ? sexToNumber(s) : Number(s)
  return v >= -90 && v <= 90 ? v : NaN
}

export function fmtRA(deg) {
  const h = deg / 15
  const hh = Math.floor(h)
  const mm = Math.floor((h - hh) * 60)
  const ss = ((h - hh) * 60 - mm) * 60
  return `${String(hh).padStart(2, '0')}h${String(mm).padStart(2, '0')}m${ss.toFixed(1).padStart(4, '0')}s`
}

export function fmtDec(deg) {
  const sign = deg < 0 ? '−' : '+'
  const a = Math.abs(deg)
  const dd = Math.floor(a)
  const mm = Math.floor((a - dd) * 60)
  const ss = ((a - dd) * 60 - mm) * 60
  return `${sign}${String(dd).padStart(2, '0')}°${String(mm).padStart(2, '0')}′${ss.toFixed(0).padStart(2, '0')}″`
}
