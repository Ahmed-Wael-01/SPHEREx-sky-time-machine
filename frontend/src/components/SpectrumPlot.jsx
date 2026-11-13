// Dependency-free SVG scatter of spectrum points. Swap for a charting library later if wanted.
import { fmtRA, fmtDec } from '../lib/coords.js'

const W = 300
const H = 170
const P = { l: 36, r: 8, t: 10, b: 26 }

export default function SpectrumPlot({ data, pos, onClick }) {
  return (
    <div className={`panel spectrum-panel ${onClick ? 'clickable' : ''}`} onClick={onClick}>
      <div className="panel-title-row">
        <h3>Spectrum</h3>
        <span className="expand-indicator" title="Click to view full 102-band spectrum and light curve">Details ↗</span>
      </div>
      <p className="muted small">{fmtRA(pos.ra)} {fmtDec(pos.dec)}</p>
      {!data && <p className="muted">Loading or unavailable…</p>}
      {data && <Plot pts={data.points} />}
      {data?.source === 'mock' && <p className="banner small">Placeholder spectrum (mock), not a measurement</p>}
    </div>
  )
}

function Plot({ pts }) {
  if (!pts?.length) return <p className="muted">No points.</p>
  const ys = pts.map((p) => p.flux_mjy)
  const yMax = Math.max(...ys.map((y, i) => y + pts[i].err_mjy)) * 1.05
  const yMin = Math.min(0, ...ys)
  const x = (wl) => P.l + ((wl - 0.7) / (5.1 - 0.7)) * (W - P.l - P.r)
  const y = (f) => H - P.b - ((f - yMin) / (yMax - yMin || 1)) * (H - P.t - P.b)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="spec" role="img" aria-label="Flux versus wavelength">
      <line x1={P.l} y1={H - P.b} x2={W - P.r} y2={H - P.b} className="axis" />
      <line x1={P.l} y1={P.t} x2={P.l} y2={H - P.b} className="axis" />
      {[1, 2, 3, 4, 5].map((t) => (
        <text key={t} x={x(t)} y={H - 8} className="tick">{t}</text>
      ))}
      <text x={W - P.r} y={P.t + 6} className="tick" textAnchor="end">wavelength (µm)</text>
      <text x={4} y={P.t + 6} className="tick">mJy</text>
      {pts.map((p, i) => (
        <g key={i} className={p.flagged ? 'flagged' : ''}>
          <line x1={x(p.wavelength_um)} x2={x(p.wavelength_um)} y1={y(p.flux_mjy - p.err_mjy)} y2={y(p.flux_mjy + p.err_mjy)} className="err" />
          <circle cx={x(p.wavelength_um)} cy={y(p.flux_mjy)} r="2" />
        </g>
      ))}
    </svg>
  )
}
