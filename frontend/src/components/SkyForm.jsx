import { useEffect, useState } from 'react'
import { TARGETS, MOCK_TARGET } from '../lib/targets.js'
import { parseRA, parseDec } from '../lib/coords.js'

export default function SkyForm({ query, fov, onFov, maxFov, onSubmit }) {
  const [ra, setRa] = useState(String(query.ra ?? ''))
  const [dec, setDec] = useState(String(query.dec ?? ''))
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (query.ra !== undefined) setRa(String(query.ra))
    if (query.dec !== undefined) setDec(String(query.dec))
  }, [query])

  const submit = (e) => {
    e.preventDefault()
    const r = parseRA(ra)
    const d = parseDec(dec)
    if (Number.isNaN(r)) return setErr('RA: degrees (0–360) or sexagesimal like 08h55m10.8s')
    if (Number.isNaN(d)) return setErr('Dec: degrees (−90 to 90) or sexagesimal like −07°14′42″')
    setErr(null)
    onSubmit({ ra: r, dec: d, fov: Number(fov) })
  }

  const pick = (t) => {
    setErr(null)
    onSubmit({ target: t.slug, ra: t.ra, dec: t.dec, fov: t.fov })
  }

  // Find currently selected target object
  const currentTarget =
    [...TARGETS, MOCK_TARGET].find((t) => t.slug === query.target) ||
    TARGETS.find(
      (t) => Math.abs(t.ra - query.ra) < 0.01 && Math.abs(t.dec - query.dec) < 0.01,
    )

  return (
    <section className="form">
      {/* Coordinate search input */}
      <form onSubmit={submit} className="coords">
        <label>
          Right Ascension (RA)
          <input
            value={ra}
            onChange={(e) => setRa(e.target.value)}
            placeholder="133.795 or 08h55m10.8s"
          />
        </label>
        <label>
          Declination (Dec)
          <input
            value={dec}
            onChange={(e) => setDec(e.target.value)}
            placeholder="-7.245 or -07:14:42.5"
          />
        </label>
        <label className="fov">
          Field of View (FoV) <b>{fov.toFixed(2)}°</b>{' '}
          <small>({Math.round(fov * 60)}′{maxFov && fov >= maxFov - 0.001 ? ', whole photo' : ''})</small>
          <input type="range" min="0.03" max={maxFov ? maxFov.toFixed(3) : 1} step="0.001"
            value={maxFov ? Math.min(fov, maxFov) : fov} onChange={(e) => onFov(Number(e.target.value))} />
        </label>
        <button type="submit" className="go">
          Inspect Sky
        </button>
      </form>
      {err && <p className="form-err">{err}</p>}


      {/* Story Mode Target Showcase Pills */}
      <div className="targets-section">
        <div className="targets-header">
          <span className="section-label">NASA Challenge Curated Test Targets:</span>
          <span className="section-hint">Click any benchmark to load SPHEREx epochs</span>
        </div>
        <div className="targets">
          {TARGETS.map((t) => (
            <button
              key={t.slug}
              type="button"
              className={`target-pill ${query.target === t.slug ? 'on' : ''}`}
              onClick={() => pick(t)}
            >
              <span className="pill-title">{t.label}</span>
              {t.tag && <span className="pill-tag">{t.tag}</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Target Scientific Spotlight Card for Judges */}
      {currentTarget && (
        <div className="target-spotlight">
          <div className="spotlight-title">
            <span className="spotlight-badge">{currentTarget.tag || 'Target'}</span>
            <strong>{currentTarget.label}</strong>
            <span className="spotlight-coords">
              (RA: {currentTarget.ra.toFixed(4)}°, Dec: {currentTarget.dec.toFixed(4)}°)
            </span>
          </div>
          <p className="spotlight-blurb">{currentTarget.blurb}</p>
          {currentTarget.tip && (
            <div className="spotlight-tip">
              💡 <b>Observer Guide:</b> {currentTarget.tip}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
