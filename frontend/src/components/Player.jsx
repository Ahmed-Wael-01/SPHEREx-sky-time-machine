import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import FrameCanvas, { loadGrey } from './FrameCanvas.jsx'
import Overlay from './Overlay.jsx'
import { COLORMAPS, DIFF_COLORMAPS, STRETCHES } from '../lib/colormaps.js'
import { makeWcs, mjdToYear } from '../lib/wcs.js'
import { fmtRA, fmtDec } from '../lib/coords.js'

// 3-colour composite: short wavelengths blue, middle green, long red
const RGB_GROUPS = { b: [1, 2], g: [3, 4], r: [5, 6] }

const OVERLAYS = [
  ['target', 'Target', '#2f6bff'],
  ['path', 'Path', '#ffd23f'],
  ['grid', 'RA/Dec grid', '#9a9a9a'],
  ['gaia', 'Gaia DR3', '#22d3ee'],
  ['allwise', 'AllWISE', '#ff7a1a'],
  ['scale', 'Scale bar', '#f5f5f5'],
]

export default function Player({ manifest, frames, deep, mode, det, idx, setIdx, onPick, clicked, catalogs }) {
  const [playing, setPlaying] = useState(true)
  const [fps, setFps] = useState(2)
  const [zoom, setZoom] = useState(1)
  const [cmap, setCmap] = useState('grey') // a COLORMAPS key, or 'rgb'
  const [dmap, setDmap] = useState('bluered')
  const [stretch, setStretch] = useState('normal')
  const [show, setShow] = useState({ target: true, path: false, grid: false, gaia: false, allwise: false, scale: true })
  const [hover, setHover] = useState(null)
  const greyRef = useRef(null)

  const isDeep = mode === 'deep'
  const isDiff = mode === 'diff'
  const frame = isDeep ? deep : frames[idx]
  const n = frames.length
  const wcs = useMemo(() => makeWcs(manifest), [manifest])
  const rgbAllowed = det === 0 && !isDiff
  const useRgb = cmap === 'rgb' && rgbAllowed

  // preload frames of the current detector/mode so playback doesn't flicker
  useEffect(() => {
    frames.forEach((f) => loadGrey(isDiff ? f.diff_url : f.image_url))
  }, [frames, isDiff])

  useEffect(() => {
    if (!playing || isDeep || n < 2) return
    const id = setInterval(() => setIdx((i) => (i + 1) % n), 1000 / fps)
    return () => clearInterval(id)
  }, [playing, fps, n, isDeep, setIdx])

  useEffect(() => {
    const onKey = (e) => {
      if (['INPUT', 'SELECT'].includes(e.target.tagName)) return
      if (e.code === 'Space') { e.preventDefault(); setPlaying((p) => !p) }
      if (e.code === 'ArrowRight') { setPlaying(false); setIdx((i) => (i + 1) % Math.max(n, 1)) }
      if (e.code === 'ArrowLeft') { setPlaying(false); setIdx((i) => (i - 1 + n) % Math.max(n, 1)) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [n, setIdx])

  // urls for each colour channel: same sky pass (epoch) as the current frame, or the deep stacks
  const rgbUrls = useMemo(() => {
    if (!useRgb || !frame) return null
    const pick = (dets) => isDeep
      ? (manifest.deep || []).filter((d) => dets.includes(d.detector)).map((d) => d.image_url)
      : manifest.visits.filter((v) => v.epoch === frame.epoch && dets.includes(v.detector)).map((v) => v.image_url)
    return { r: pick(RGB_GROUPS.r), g: pick(RGB_GROUPS.g), b: pick(RGB_GROUPS.b) }
  }, [useRgb, frame, isDeep, manifest])

  const fracFromEvent = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    return { fx: (e.clientX - r.left) / r.width, fy: (e.clientY - r.top) / r.height }
  }

  const click = (e) => {
    const { fx, fy } = fracFromEvent(e)
    onPick({ ...wcs.toSky(fx, fy), fx, fy })
  }

  const move = (e) => {
    const { fx, fy } = fracFromEvent(e)
    const g = greyRef.current
    let level = null
    if (g) {
      const x = Math.floor(fx * g.w)
      const y = Math.floor(fy * g.h)
      if (x >= 0 && y >= 0 && x < g.w && y < g.h) level = g.alpha[y * g.w + x] ? g.data[y * g.w + x] : 'no data'
    }
    setHover({ ...wcs.toSky(fx, fy), level })
  }

  const onGrey = useCallback((g) => { greyRef.current = g }, [])

  if (!frame) return <div className="empty">No frames for this detector.</div>

  const src = isDiff ? frame.diff_url : frame.image_url
  const lutName = isDiff ? dmap : (cmap === 'rgb' ? 'grey' : cmap)
  const lut = (isDiff ? DIFF_COLORMAPS : COLORMAPS)[lutName]?.lut ?? COLORMAPS.grey.lut
  const gamma = STRETCHES[stretch].gamma
  const epochYear = frame.mjd ? mjdToYear(frame.mjd) : 2026.0
  const pathFrames = frames.length ? frames : []

  return (
    <div className="player">
      <div className="frame-box">
        <div className="frame-inner" style={{ transform: `scale(${zoom})` }} onClick={click}
          onMouseMove={move} onMouseLeave={() => setHover(null)}>
          {useRgb && rgbUrls ? (
            <FrameCanvas rgb={{ ...rgbUrls, gamma }} onGrey={onGrey} alt={`3-colour SPHEREx frame ${frame.date || 'deep stack'}`} />
          ) : src ? (
            <FrameCanvas single={{ url: src, lut, lutName, gamma }} onGrey={onGrey} alt={`SPHEREx frame ${frame.date || 'deep stack'}`} />
          ) : (
            <div className="empty">No difference image (only one visit)</div>
          )}
          <Overlay manifest={manifest} wcs={wcs} show={show} frame={isDeep ? null : frame} pathFrames={pathFrames}
            catalogs={catalogs} epochYear={epochYear} clicked={clicked} />
        </div>
        <div className="stamp">
          {isDeep ? `Deep stack · ${frame.n_exposures} exposures` : `${frame.date} · visit ${idx + 1}/${n}`}
          {useRgb && <span className="rgb-key"> · <b style={{ color: '#6f8cff' }}>B</b> 0.75–1.6 <b style={{ color: '#4ade80' }}>G</b> 1.6–3.8 <b style={{ color: '#ff6b5a' }}>R</b> 3.8–5 µm</span>}
        </div>
        <div className="compass" aria-hidden>N ↑ · E ←</div>
        {hover && (
          <div className="readout">
            {fmtRA(hover.ra)} {fmtDec(hover.dec)}
            {hover.level !== null && !useRgb && <span> · {typeof hover.level === 'number' ? `level ${hover.level}` : 'no data'}</span>}
          </div>
        )}
      </div>

      <div className="controls">
        <button onClick={() => setPlaying((p) => !p)} disabled={isDeep || n < 2} className="play">
          {playing && !isDeep && n > 1 ? 'Pause' : 'Play'}
        </button>
        <input type="range" min="0" max={Math.max(n - 1, 0)} value={idx} disabled={isDeep}
          onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)) }} aria-label="Visit date" />
        <label>
          Speed
          <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
            {[0.5, 1, 2, 4, 8].map((v) => <option key={v} value={v}>{v} fps</option>)}
          </select>
        </label>
        <label>
          Zoom
          <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
            {[1, 2, 4].map((v) => <option key={v} value={v}>{v}×</option>)}
          </select>
        </label>
      </div>

      <div className="controls look">
        <label>
          Colour
          {isDiff ? (
            <select value={dmap} onChange={(e) => setDmap(e.target.value)}>
              {Object.entries(DIFF_COLORMAPS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          ) : (
            <select value={cmap} onChange={(e) => setCmap(e.target.value)}>
              {Object.entries(COLORMAPS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              <option value="rgb" disabled={!rgbAllowed}>3-colour infrared{rgbAllowed ? '' : ' (choose All)'}</option>
            </select>
          )}
        </label>
        <label>
          Contrast
          <select value={stretch} onChange={(e) => setStretch(e.target.value)}>
            {Object.entries(STRETCHES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </label>
        <div className="chips" role="group" aria-label="Overlays">
          {OVERLAYS.map(([k, label, color]) => {
            const missing = (k === 'gaia' && !catalogs?.gaia) || (k === 'allwise' && !catalogs?.allwise)
            return (
              <button key={k} className={`chip ${show[k] && !missing ? 'on' : ''}`} disabled={missing}
                title={missing ? 'No catalogue for this target yet (run science/fetch_catalogs.py)' : ''}
                onClick={() => setShow((s) => ({ ...s, [k]: !s[k] }))}>
                <i style={{ background: color }} />{label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="dates">
        {frames.map((f, i) => (
          <button key={f.image_url} className={i === idx && !isDeep ? 'on' : ''}
            onClick={() => { setPlaying(false); setIdx(i) }}>{f.date}</button>
        ))}
      </div>
    </div>
  )
}
