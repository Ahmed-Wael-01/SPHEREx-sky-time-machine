// Parse RA/Dec typed as degrees ("133.795") or sexagesimal ("08h55m10.8s", "08:55:10.8", "08 55 10.8").
// RA sexagesimal is hours; Dec sexagesimal is degrees.

function sexToNumber(str) {
  str = str.replace(/[−–—]/g, '-')
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
  s = String(s).replace(/[−–—]/g, '-')
  const v = isSex(s) ? sexToNumber(s) * 15 : Number(s)
  return v >= 0 && v < 360 ? v : NaN
}

export function parseDec(s) {
  if (s == null || String(s).trim() === '') return NaN
  s = String(s).replace(/[−–—]/g, '-')
  const v = isSex(s) ? sexToNumber(s) : Number(s)
  return v >= -90 && v <= 90 ? v : NaN
}

export function fmtRA(deg) {
  // work in whole tenths of a second of time so rounding can never print "60.0s"
  const t = Math.round((((deg % 360) + 360) % 360) / 15 * 36000) % (24 * 36000)
  const hh = Math.floor(t / 36000)
  const mm = Math.floor((t % 36000) / 600)
  const ss = (t % 600) / 10
  return `${String(hh).padStart(2, '0')}h${String(mm).padStart(2, '0')}m${ss.toFixed(1).padStart(4, '0')}s`
}

export function fmtDec(deg) {
  // whole arcseconds, so 15'59.99" becomes 16'00" instead of 15'60"
  const sign = deg < 0 ? '−' : '+'
  const t = Math.round(Math.abs(deg) * 3600)
  const dd = Math.floor(t / 3600)
  const mm = Math.floor((t % 3600) / 60)
  const ss = t % 60
  return `${sign}${String(dd).padStart(2, '0')}°${String(mm).padStart(2, '0')}′${String(ss).padStart(2, '0')}″`
}
