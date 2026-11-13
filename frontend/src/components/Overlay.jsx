// SVG layer on top of the frame: grid, target path, predicted position, catalogue sources, scale bar.
// Coordinates are image fractions scaled to a 1000 x 1000 viewBox, so it follows zoom.
import { useMemo } from 'react'
import { gridLines, propagate, mjdToYear } from '../lib/wcs.js'
import { fmtRA, fmtDec } from '../lib/coords.js'

const V = 1000
const inside = (p) => p && p.fx > -0.02 && p.fx < 1.02 && p.fy > -0.02 && p.fy < 1.02

export default function Overlay({ manifest, wcs, show, frame, pathFrames, catalogs, epochYear, clicked }) {
  const grid = useMemo(() => (show.grid ? gridLines(wcs, manifest) : null), [show.grid, wcs, manifest])

  const gaia = useMemo(() => {
    if (!show.gaia || !catalogs?.gaia) return []
    const c = catalogs.gaia
    return c.rows
      .map(([ra, dec, pmra, pmdec, g]) => ({ ...wcs.toFrac(...Object.values(propagate(ra, dec, pmra || 0, pmdec || 0, c.epoch, epochYear))), g }))
      .filter(inside)
  }, [show.gaia, catalogs, wcs, epochYear])

  const wise = useMemo(() => {
    if (!show.allwise || !catalogs?.allwise) return []
    return catalogs.allwise.rows.map(([ra, dec, w1, w2]) => ({ ...wcs.toFrac(ra, dec), w2 })).filter(inside)
  }, [show.allwise, catalogs, wcs])

  const pred = frame?.predicted
  const path = show.path ? pathFrames.filter((f) => f.predicted).map((f) => f.predicted) : []
  const pxFrac = 1 / manifest.pixels

  // scale bar: 1 arcmin, or 30" for small fields
  const barArcsec = wcs.span * 3600 > 400 ? 60 : 30
  const barFrac = barArcsec / 3600 / wcs.span

  return (
    <svg className="overlay" viewBox={`0 0 ${V} ${V}`} preserveAspectRatio="none" aria-hidden>
      {grid && (
        <g className="ov-grid">
          {grid.lines.map((l, i) => (
            <polyline key={i} points={l.pts.map((p) => `${p.fx * V},${p.fy * V}`).join(' ')} />
          ))}
          {grid.lines.map((l, i) => {
            const p = l.kind === 'dec'
              ? l.pts.find((q) => q.fx > 0.01 && q.fx < 0.2 && q.fy > 0.03 && q.fy < 0.97)
              : l.pts.find((q) => q.fy > 0.86 && q.fy < 0.98 && q.fx > 0.03 && q.fx < 0.97)
            if (!p) return null
            return (
              <text key={`t${i}`} x={p.fx * V + 6} y={p.fy * V - 6} className="ov-label">
                {l.kind === 'dec' ? fmtDec(l.value).slice(0, 7) : fmtRA(l.value).slice(0, 6)}
              </text>
            )
          })}
        </g>
      )}

      {gaia.map((s, i) => (
        <circle key={`g${i}`} cx={s.fx * V} cy={s.fy * V} r={Math.max(4, 14 - (s.g ?? 18) * 0.5)} className="ov-gaia" />
      ))}
      {wise.map((s, i) => (
        <rect key={`w${i}`} x={s.fx * V - 7} y={s.fy * V - 7} width="14" height="14" className="ov-wise" />
      ))}

      {path.length > 1 && (
        <g className="ov-path">
          <polyline points={path.map((p) => `${p.fx * V},${p.fy * V}`).join(' ')} />
          {path.map((p, i) => <circle key={i} cx={p.fx * V} cy={p.fy * V} r="3" />)}
        </g>
      )}

      {show.target && pred && (
        <circle cx={pred.fx * V} cy={pred.fy * V} r={pxFrac * V * 2.2} className="ov-target">
          <title>Predicted position of the target on this date (from proper motion)</title>
        </circle>
      )}

      {clicked && (
        <g className="ov-pick">
          <line x1={clicked.fx * V - 12} x2={clicked.fx * V + 12} y1={clicked.fy * V} y2={clicked.fy * V} />
          <line x1={clicked.fx * V} x2={clicked.fx * V} y1={clicked.fy * V - 12} y2={clicked.fy * V + 12} />
        </g>
      )}

      {show.scale && (
        <g className="ov-scale">
          <line x1={V - 30 - barFrac * V} x2={V - 30} y1={V - 30} y2={V - 30} />
          <text x={V - 30 - (barFrac * V) / 2} y={V - 42} textAnchor="middle">{barArcsec === 60 ? '1′' : '30″'}</text>
        </g>
      )}
    </svg>
  )
}
