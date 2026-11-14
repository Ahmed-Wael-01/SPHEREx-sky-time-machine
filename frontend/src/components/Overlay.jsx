// SVG layer on top of the frame: grid, target path, predicted position, catalogue sources, scale bar.
// Coordinates are image fractions scaled to a 1000 x 1000 viewBox, so it follows zoom.
import { useMemo } from 'react'
import { gridLines, propagate, mjdToYear } from '../lib/wcs.js'
import { fmtRA, fmtDec } from '../lib/coords.js'

const V = 1000
// show seconds only when the grid is finer than 1 arcmin (Dec) or 1 minute of time (RA)
const decLabel = (v, step) => {
  const r = Math.round(v * 3600) / 3600 // whole arcseconds, so float error can't turn 16′ into 15′59.99″
  return step >= 1 / 60 - 1e-9 ? fmtDec(r).slice(0, 7) : fmtDec(r)
}
const raLabel = (v, raStep) => {
  const r = Math.round(v * 240) / 240 // whole seconds of time
  return raStep * 240 >= 60 - 1e-6 ? fmtRA(r).slice(0, 6) : fmtRA(r).slice(0, 8) + 's'
}
const inside = (p) => p && p.fx > -0.02 && p.fx < 1.02 && p.fy > -0.02 && p.fy < 1.02

export default function Overlay({ manifest, wcs, show, frame, pathFrames, catalogs, epochYear, clicked, scale = 1 }) {
  const grid = useMemo(() => (show.grid ? gridLines(wcs, manifest, scale) : null), [show.grid, wcs, manifest, scale])
  const k = 1 / scale // keeps markers and text the same size on screen at any zoom
  const lo = 0.5 - 0.5 * k
  const hi = 0.5 + 0.5 * k
  const w = hi - lo

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

  // mover-finder hits on this pass (all passes on the deep stack); one marker per detector
  const dets = useMemo(() => {
    const d = catalogs?.detections
    if (!show.detections || !d) return []
    return d.candidates
      .filter((c) => frame == null || c.epoch === frame.epoch)
      .map((c) => ({ ...c, ...wcs.toFrac(c.ra, c.dec) }))
      .filter(inside)
  }, [show.detections, catalogs, wcs, frame])

  const pred = frame?.predicted
  const path = show.path ? pathFrames.filter((f) => f.predicted).map((f) => f.predicted) : []
  const pxFrac = 1 / manifest.pixels


  return (
    <svg className="overlay" viewBox={`0 0 ${V} ${V}`} preserveAspectRatio="none" aria-hidden>
      {grid && (
        <g className="ov-grid">
          {grid.lines.map((l, i) => (
            <polyline key={i} points={l.pts.map((p) => `${p.fx * V},${p.fy * V}`).join(' ')} />
          ))}
          {grid.lines.map((l, i) => {
            const p = l.kind === 'dec'
              ? l.pts.find((q) => q.fx > lo + 0.01 * w && q.fx < lo + 0.25 * w && q.fy > lo + 0.05 * w && q.fy < hi - 0.03 * w)
              : l.pts.find((q) => q.fy > lo + 0.03 * w && q.fy < lo + 0.12 * w && q.fx > lo + 0.08 * w && q.fx < hi - 0.3 * w)
            if (!p) return null
            return (
              <text key={`t${i}`} x={p.fx * V + 6 * k} y={p.fy * V - 6 * k} className="ov-label" style={{ fontSize: 22 * k, strokeWidth: 3 * k }}>
                {l.kind === 'dec' ? decLabel(l.value, grid.step) : raLabel(l.value, grid.raStep)}
              </text>
            )
          })}
        </g>
      )}

      {gaia.map((s, i) => (
        <circle key={`g${i}`} cx={s.fx * V} cy={s.fy * V} r={Math.max(4, 14 - (s.g ?? 18) * 0.5) * k} className="ov-gaia" />
      ))}
      {wise.map((s, i) => (
        <rect key={`w${i}`} x={s.fx * V - 7 * k} y={s.fy * V - 7 * k} width={14 * k} height={14 * k} className="ov-wise" />
      ))}

      {path.length > 1 && (
        <g className="ov-path">
          <polyline points={path.map((p) => `${p.fx * V},${p.fy * V}`).join(' ')} />
          {path.map((p, i) => <circle key={i} cx={p.fx * V} cy={p.fy * V} r={3 * k} />)}
        </g>
      )}

      {dets.map((c, i) => {
        const r = pxFrac * V * 3.4
        return (
          <g key={`d${i}`} className="ov-det">
            <path d={`M${c.fx * V} ${c.fy * V - r} L${c.fx * V + r} ${c.fy * V} L${c.fx * V} ${c.fy * V + r} L${c.fx * V - r} ${c.fy * V} Z`} />
            <title>{`Mover finder: ${c.known_match || 'unmatched candidate'} on ${c.date} (detector ${c.detector}), ${c.offset_px ?? '?'} px from the predicted position`}</title>
          </g>
        )
      })}

      {show.target && pred && (
        <circle cx={pred.fx * V} cy={pred.fy * V} r={pxFrac * V * 2.2} className="ov-target">
          <title>Predicted position of the target on this date (from proper motion)</title>
        </circle>
      )}

      {clicked && (
        <g className="ov-pick">
          <line x1={clicked.fx * V - 12 * k} x2={clicked.fx * V + 12 * k} y1={clicked.fy * V} y2={clicked.fy * V} />
          <line x1={clicked.fx * V} x2={clicked.fx * V} y1={clicked.fy * V - 12 * k} y2={clicked.fy * V + 12 * k} />
        </g>
      )}

    </svg>
  )
}
