import React, { useState } from 'react'
import { fmtRA, fmtDec } from '../lib/coords.js'

// Prominent IR molecular absorption features across SPHEREx's 0.75 - 5.0 µm bandpass
const SPECTRAL_FEATURES = [
  { label: 'H₂O', wl: 1.4, desc: 'Water vapor band' },
  { label: 'H₂O', wl: 1.9, desc: 'Water vapor band' },
  { label: 'CO₂ / Ice', wl: 2.7, desc: 'Water ice & CO₂' },
  { label: 'CH₄ (Methane)', wl: 3.3, desc: 'Methane dip (Brown Dwarf hallmark)' },
  { label: 'CO', wl: 4.67, desc: 'Carbon Monoxide band' },
]

export default function ObjectDetailModal({ pos, data, simbad, onClose }) {
  const [activeTab, setActiveTab] = useState('spectrum') // 'spectrum' | 'lightcurve'

  if (!pos) return null

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-window" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>Object Spectral & Photometric Analysis</h3>
            <p className="coord-subtitle">
              Clicked Position: <b>{fmtRA(pos.ra)}</b> {fmtDec(pos.dec)}
              {data?.name && <span className="target-chip"> · {data.name}</span>}
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">✕</button>
        </div>

        {/* Live SIMBAD Astrometric Cross-Match Identification */}
        <div className="simbad-card">
          <div className="simbad-header">
            <span className="simbad-pill">SIMBAD Astro Match</span>
            {simbad === null && <span className="simbad-querying">Resolving coordinates with SIMBAD…</span>}
            {simbad?.match && (
              <span className="simbad-matched">
                ✓ Known Object: <b>{simbad.identifier}</b> ({simbad.otype} {simbad.sp_type && `· ${simbad.sp_type}`}) · {simbad.dist_arcsec}″ away
                {simbad.url && (
                  <a href={simbad.url} target="_blank" rel="noreferrer" className="simbad-link">
                    SIMBAD Details ↗
                  </a>
                )}
              </span>
            )}
            {simbad && simbad.match === false && (
              <span className="simbad-querying">
                No SIMBAD object within 0.8′. Many faint stars are not in SIMBAD, so this alone is not a discovery.
              </span>
            )}
            {simbad && simbad.match == null && simbad.error !== undefined && (
              <span className="simbad-querying">
                {import.meta.env.VITE_STATIC === '1'
                  ? 'Object lookup (SIMBAD) needs our live server; this public copy of the site runs without it.'
                  : 'SIMBAD lookup unavailable right now.'}
              </span>
            )}
          </div>
        </div>

        <div className="modal-tabs">
          <button
            className={activeTab === 'spectrum' ? 'tab-btn active' : 'tab-btn'}
            onClick={() => setActiveTab('spectrum')}
          >
            102-Band IR Spectrum (0.75 – 5.0 µm)
          </button>
          <button
            className={activeTab === 'lightcurve' ? 'tab-btn active' : 'tab-btn'}
            onClick={() => setActiveTab('lightcurve')}
          >
            Multi-Epoch Light Curve (Variability)
          </button>
        </div>

        <div className="modal-body">
          {activeTab === 'spectrum' ? (
            <SpectrumView points={data?.points} note={data?.note} />
          ) : (
            <LightCurveView lightCurve={data?.light_curve} band={data?.light_curve_band} verdict={data?.variability?.text} />
          )}
        </div>

        <div className="modal-footer">
          <span className="badge-source">
            {data?.source === 'mock'
              ? '⚠️ Showing synthetic test points (mock)'
              : '✓ SPHEREx 102-channel LVF Aperture Photometry'}
          </span>
          <button
            type="button"
            className="export-btn"
            onClick={() => downloadCSV(data, pos)}
            disabled={!data?.points?.length}
          >
            Export Spectral Data (CSV)
          </button>
        </div>
      </div>
    </div>
  )
}

function SpectrumView({ points, note }) {
  if (!points?.length) {
    return <div className="chart-empty">{note || 'No spectrum measured at this position.'}</div>
  }

  const W = 620
  const H = 250
  const P = { l: 52, r: 24, t: 30, b: 38 }
  const ys = points.map((p) => p.flux_mjy)
  const yMax = Math.max(...ys.map((y, i) => y + (points[i].err_mjy || 0))) * 1.15 || 1
  // measurements can dip below zero (a faint object plus noise), so let the axis go there too
  const yMin = Math.min(0, ...ys.map((y, i) => y - (points[i].err_mjy || 0)))

  const xMap = (wl) => P.l + ((wl - 0.75) / (5.0 - 0.75)) * (W - P.l - P.r)
  const yMap = (f) => H - P.b - ((f - yMin) / (yMax - yMin || 1)) * (H - P.t - P.b)

  return (
    <div className="chart-container">
      <div className="chart-legend-top">
        <span>● Photometry Point</span>
        <span style={{ color: '#ffb020' }}>● Flagged Channel (Artifact / Contamination)</span>
        <span style={{ color: '#888' }}>┆ Key Atmospheric Molecular Markers</span>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="analysis-svg" role="img" aria-label="102-band infrared spectrum">
        {/* Molecular Band Vertical Lines */}
        {SPECTRAL_FEATURES.map((feat, i) => {
          const x = xMap(feat.wl)
          return (
            <g key={i} className="marker-band">
              <line x1={x} y1={P.t} x2={x} y2={H - P.b} strokeDasharray="3 3" stroke="#383838" />
              <text x={x} y={P.t - 8} textAnchor="middle" fill="#999" fontSize="10">
                {feat.label}
              </text>
            </g>
          )
        })}

        {/* Axes */}
        <line x1={P.l} y1={H - P.b} x2={W - P.r} y2={H - P.b} stroke="#444" strokeWidth="1.5" />
        <line x1={P.l} y1={P.t} x2={P.l} y2={H - P.b} stroke="#444" strokeWidth="1.5" />

        {/* X Ticks & Labels */}
        {[1.0, 2.0, 3.0, 4.0, 5.0].map((t) => (
          <g key={t}>
            <line x1={xMap(t)} y1={H - P.b} x2={xMap(t)} y2={H - P.b + 5} stroke="#666" />
            <text x={xMap(t)} y={H - P.b + 18} fill="#999" fontSize="11" textAnchor="middle">
              {t.toFixed(1)} µm
            </text>
          </g>
        ))}

        {yMin < 0 && <line x1={P.l} x2={W - P.r} y1={yMap(0)} y2={yMap(0)} stroke="#555" strokeDasharray="2 3" />}
        {/* Y Axis Ticks */}
        {[yMin < 0 ? yMin : 0, yMax * 0.5, yMax].map((val, idx) => (
          <g key={idx}>
            <text x={P.l - 8} y={yMap(val) + 4} fill="#888" fontSize="10" textAnchor="end">
              {val.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Y Axis Title */}
        <text x={12} y={P.t + 4} fill="#888" fontSize="10" transform={`rotate(-90, 12, ${P.t + 4})`}>
          Flux (mJy)
        </text>

        {/* Spectrum Data Points with Error Bars */}
        {points.map((p, idx) => (
          <g key={idx}>
            {p.err_mjy && (
              <line
                x1={xMap(p.wavelength_um)}
                x2={xMap(p.wavelength_um)}
                y1={yMap(p.flux_mjy - p.err_mjy)}
                y2={yMap(p.flux_mjy + p.err_mjy)}
                stroke="rgba(47, 107, 255, 0.45)"
                strokeWidth="1.2"
              />
            )}
            <circle
              cx={xMap(p.wavelength_um)}
              cy={yMap(p.flux_mjy)}
              r="2.5"
              fill={p.flagged ? '#ffb020' : '#2f6bff'}
            >
              <title>{`${p.wavelength_um} µm: ${p.flux_mjy} mJy (Det ${p.detector}${p.flagged ? ', Flagged' : ''})`}</title>
            </circle>
          </g>
        ))}
      </svg>
    </div>
  )
}

function LightCurveView({ lightCurve, band, verdict }) {
  if (!lightCurve?.length) {
    return (
      <div className="chart-empty">
        No multi-epoch light curve points recorded for this aperture.
      </div>
    )
  }

  const W = 620
  const H = 220
  const P = { l: 52, r: 30, t: 25, b: 40 }
  const fluxes = lightCurve.map((d) => d.flux_mjy)
  // axis from zero (or below), so small changes don't look dramatic; error bars show what is noise
  const minF = Math.min(0, ...lightCurve.map((d) => d.flux_mjy - (d.err_mjy || 0)))
  const maxF = Math.max(...lightCurve.map((d) => d.flux_mjy + (d.err_mjy || 0))) * 1.15 || 1

  const xMap = (idx) => P.l + (idx / Math.max(lightCurve.length - 1, 1)) * (W - P.l - P.r)
  const yMap = (f) => H - P.b - ((f - minF) / (maxF - minF || 1)) * (H - P.t - P.b)

  return (
    <div className="chart-container">
      <div className="chart-legend-top">
        <span>Brightness on each SPHEREx sky pass{band ? `, ${band} (same colour range every pass)` : ''}</span>
      </div>
      {verdict && <p className="muted small" style={{ margin: '4px 0 0' }}>Verdict: {verdict}.</p>}

      <svg viewBox={`0 0 ${W} ${H}`} className="analysis-svg" role="img" aria-label="Multi-epoch light curve">
        <line x1={P.l} y1={H - P.b} x2={W - P.r} y2={H - P.b} stroke="#444" strokeWidth="1.5" />
        <line x1={P.l} y1={P.t} x2={P.l} y2={H - P.b} stroke="#444" strokeWidth="1.5" />

        {/* Connecting line */}
        <polyline
          fill="none"
          stroke="#2f6bff"
          strokeWidth="2.5"
          points={lightCurve.map((pt, i) => `${xMap(i)},${yMap(pt.flux_mjy)}`).join(' ')}
        />

        {lightCurve.map((pt, i) => (
          <g key={i}>
            {pt.err_mjy > 0 && (
              <line x1={xMap(i)} x2={xMap(i)} y1={yMap(pt.flux_mjy - pt.err_mjy)} y2={yMap(pt.flux_mjy + pt.err_mjy)}
                stroke="rgba(47, 107, 255, 0.6)" strokeWidth="1.5" />
            )}
            <circle cx={xMap(i)} cy={yMap(pt.flux_mjy)} r="5" fill="#ffffff" stroke="#2f6bff" strokeWidth="2" />
            <text x={xMap(i)} y={H - P.b + 18} fill="#999" fontSize="11" textAnchor="middle">
              {pt.date}
            </text>
            <text x={xMap(i)} y={yMap(pt.flux_mjy) - 10} fill="#ffffff" fontSize="10" textAnchor="middle">
              {pt.flux_mjy.toFixed(2)} mJy
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

function downloadCSV(data, pos) {
  if (!data?.points?.length) return
  const headers = 'wavelength_um,flux_mjy,err_mjy,detector,flagged\n'
  const rows = data.points
    .map((p) => `${p.wavelength_um},${p.flux_mjy},${p.err_mjy},${p.detector},${p.flagged}`)
    .join('\n')
  const blob = new Blob([headers + rows], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `spherex_spec_${pos.ra.toFixed(4)}_${pos.dec.toFixed(4)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

