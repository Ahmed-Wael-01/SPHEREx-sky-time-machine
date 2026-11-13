import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import FrameCanvas, { loadGrey } from './FrameCanvas.jsx'
import Overlay from './Overlay.jsx'
import { COLORMAPS, DIFF_COLORMAPS, STRETCHES } from '../lib/colormaps.js'
import { makeWcs, mjdToYear } from '../lib/wcs.js'
import { fmtRA, fmtDec } from '../lib/coords.js'

// 3-colour composite: short wavelengths blue, middle green, long red
const RGB_GROUPS = { b: [1, 2], g: [3, 4], r: [5, 6] }

const OVERLAYS = [
  ['closeup', 'Close-up', '#f5f5f5'],
  ['target', 'Target', '#2f6bff'],
  ['path', 'Path', '#ffd23f'],
  ['grid', 'RA/Dec grid', '#9a9a9a'],
  ['gaia', 'Gaia DR3', '#22d3ee'],
  ['allwise', 'AllWISE', '#ff7a1a'],
  ['scale', 'Scale bar', '#f5f5f5'],
]

// Scale bar outside the zoomed layer so it stays in the corner; length is true on the sky.
function ScaleBar({ span, scale }) {
  const visibleArcsec = (span / scale) * 3600
  const options = [5, 10, 15, 30, 60, 120, 300, 600, 1200]
  const arcsec = options.reduce((best, o) =>
    Math.abs(o - visibleArcsec * 0.2) < Math.abs(best - visibleArcsec * 0.2) ? o : best,
  )
  const pct = (arcsec / visibleArcsec) * 100
  const label = arcsec >= 60 ? `${arcsec / 60}′` : `${arcsec}″`
  return (
    <div className="scalebar" style={{ width: `${pct}%` }}>
      <span>{label}</span>
    </div>
  )
}

// Close-up box in the corner: the same frame magnified around the target, with its predicted ring.
export const LOUPE_ARCMIN = 1.2
function Loupe({ center, span, pixels, pred, track, children }) {
  const W = ((span * 60) / LOUPE_ARCMIN) * 100 // size of the full frame, in % of the box
  const ring = pred ? { cx: pred.fx * 1000, cy: pred.fy * 1000, r: (1.8 / pixels) * 1000 } : null
  const first = track?.[0]
  const tick = (12 / W) * 1000 // fixed mark size, in frame units
  return (
    <div className="loupe" aria-hidden>
      <div className="loupe-inner" style={{ width: `${W}%`, height: `${W}%`, left: `${50 - center.fx * W}%`, top: `${50 - center.fy * W}%` }}>
        {children}
        <svg className="overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none">
          {track?.length > 1 && (
            <g className="ov-path">
              <polyline points={track.map((p) => `${p.fx * 1000},${p.fy * 1000}`).join(' ')} />
            </g>
          )}
          {first && (
            <g className="loupe-ref">
              <line x1={first.fx * 1000} x2={first.fx * 1000} y1={first.fy * 1000 - 4 * tick} y2={first.fy * 1000 - 2 * tick} />
              <line x1={first.fx * 1000} x2={first.fx * 1000} y1={first.fy * 1000 + 2 * tick} y2={first.fy * 1000 + 4 * tick} />
            </g>
          )}
          {ring && <circle cx={ring.cx} cy={ring.cy} r={ring.r} className="ov-target" />}
        </svg>
      </div>
      <span className="loupe-label">Close-up {LOUPE_ARCMIN}′ · yellow = where it was first</span>
    </div>
  )
}

export default function Player({
  manifest,
  frames,
  deep,
  mode,
  setMode,
  det = 0,
  idx,
  setIdx,
  onPick,
  clicked,
  catalogs,
  viewFov,
}) {
  const [playing, setPlaying] = useState(true)
  const [fps, setFps] = useState(2)
  const [zoom, setZoom] = useState(1)
  const [cmap, setCmap] = useState('grey') // a COLORMAPS key, or 'rgb'
  const [dmap, setDmap] = useState('bluered')
  const [stretch, setStretch] = useState('normal')
  const [show, setShow] = useState({
    closeup: true,
    target: true,
    path: false,
    grid: false,
    gaia: false,
    allwise: false,
    scale: true,
  })
  const [hover, setHover] = useState(null)
  const [isBlinking, setIsBlinking] = useState(false) // short flash on keypress
  const [blink, setBlink] = useState(false) // flip between the first and last pass only: the biggest time gap
  const greyRef = useRef(null)

  const isDeep = mode === 'deep'
  const isDiff = mode === 'diff'
  const frame = isDeep ? deep : frames[idx]
  const n = frames.length
  const wcs = useMemo(() => makeWcs(manifest), [manifest])
  const rgbAllowed = det === 0 && !isDiff
  // crop to the chosen field of view, then apply the zoom menu on top
  const scale = (viewFov ? wcs.span / viewFov : 1) * zoom
  const useRgb = cmap === 'rgb' && rgbAllowed

  // preload frames of the current detector/mode so playback doesn't flicker
  useEffect(() => {
    frames.forEach((f) => [].concat(isDiff ? f.diff_url : f.image_url).forEach((u) => u && loadGrey(u)))
  }, [frames, isDiff])

  // Playback loop
  useEffect(() => {
    if (!playing || isDeep || n < 2) return
    const id = setInterval(() => setIdx((i) => (blink ? (i === 0 ? n - 1 : 0) : (i + 1) % n)), 1000 / fps)
    return () => clearInterval(id)
  }, [playing, fps, n, isDeep, setIdx, blink])

  // Astronomical hotkeys: Space, Arrows, 'B' (Blink), 'D' (Diff mode toggle)
  useEffect(() => {
    const onKey = (e) => {
      if (['INPUT', 'SELECT'].includes(e.target.tagName)) return
      if (e.code === 'Space') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (e.code === 'ArrowRight') {
        setPlaying(false)
        setIdx((i) => (i + 1) % Math.max(n, 1))
      } else if (e.code === 'ArrowLeft') {
        setPlaying(false)
        setIdx((i) => (i - 1 + n) % Math.max(n, 1))
      } else if (e.key === 'b' || e.key === 'B') {
        setPlaying(false)
        setIdx((i) => (i === 0 ? Math.min(1, n - 1) : 0))
        setIsBlinking(true)
        setTimeout(() => setIsBlinking(false), 300)
      } else if ((e.key === 'd' || e.key === 'D') && setMode) {
        setMode((m) => (m === 'diff' ? 'frames' : 'diff'))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [n, setIdx, setMode])

  // urls for each colour channel: same sky pass (epoch) as the current frame, or the deep stacks
  const rgbUrls = useMemo(() => {
    if (!useRgb || !frame) return null
    const pick = (dets) =>
      isDeep
        ? (manifest.deep || []).filter((d) => dets.includes(d.detector)).map((d) => d.image_url)
        : manifest.visits
            .filter((v) => v.epoch === frame.epoch && dets.includes(v.detector))
            .map((v) => v.image_url)
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
      if (x >= 0 && y >= 0 && x < g.w && y < g.h) {
        level = g.alpha[y * g.w + x] ? g.data[y * g.w + x] : 'no data'
      }
    }
    setHover({ ...wcs.toSky(fx, fy), level })
  }

  const onGrey = useCallback((g) => {
    greyRef.current = g
  }, [])

  // magnifier: fixed on the target's average position, so the target visibly moves inside it
  const loupeCenter = useMemo(() => {
    const ps = frames.map((f) => f.predicted).filter(Boolean)
    if (!ps.length) return { fx: 0.5, fy: 0.5 }
    return { fx: ps.reduce((a, p) => a + p.fx, 0) / ps.length, fy: ps.reduce((a, p) => a + p.fy, 0) / ps.length }
  }, [frames])

  if (!frame) return <div className="empty">No frames available for this detector.</div>

  const src = isDiff ? frame.diff_url : frame.image_url
  const hasSrc = Array.isArray(src) ? src.length > 0 : !!src
  const lutName = isDiff ? dmap : (cmap === 'rgb' ? 'grey' : cmap)
  const lut = (isDiff ? DIFF_COLORMAPS : COLORMAPS)[lutName]?.lut ?? COLORMAPS.grey.lut
  const gamma = STRETCHES[stretch].gamma
  const epochYear = frame.mjd ? mjdToYear(frame.mjd) : 2026.0
  const pathFrames = frames.length ? frames : []

  return (
    <div className="player">
      <div className={`frame-box ${isBlinking ? 'blink-active' : ''}`}>
        <div
          className="frame-inner"
          style={{ transform: `scale(${scale})` }}
          onClick={click}
          onMouseMove={move}
          onMouseLeave={() => setHover(null)}
          title="Click to inspect 102-band infrared spectrum & light curve at this position"
        >
          {useRgb && rgbUrls ? (
            <FrameCanvas rgb={{ ...rgbUrls, gamma }} onGrey={onGrey} alt={`3-colour SPHEREx frame ${frame.date || 'deep stack'}`} />
          ) : hasSrc ? (
            <FrameCanvas single={{ url: src, lut, lutName, gamma }} onGrey={onGrey} alt={`SPHEREx frame ${frame.date || 'deep stack'}`} />
          ) : (
            <div className="empty">No difference image (only one visit)</div>
          )}
          <Overlay
            manifest={manifest}
            wcs={wcs}
            show={show}
            frame={isDeep ? null : frame}
            pathFrames={pathFrames}
            catalogs={catalogs}
            epochYear={epochYear}
            clicked={clicked}
            scale={scale}
          />
        </div>

        <div className="stamp">
          {isDeep
            ? `Deep stack · ${frame.n_exposures} exposures`
            : `${frame.date} (MJD ${frame.mjd ? frame.mjd.toFixed(1) : '—'}) · visit ${idx + 1}/${n}`}
          {useRgb && (
            <span className="rgb-key">
              {' '}
              · <b style={{ color: '#6f8cff' }}>B</b> 0.75–1.6{' '}
              <b style={{ color: '#4ade80' }}>G</b> 1.6–3.8{' '}
              <b style={{ color: '#ff6b5a' }}>R</b> 3.8–5 µm
            </span>
          )}
        </div>
        <div className="compass" aria-hidden>
          N ↑ · E ← · {((wcs.span / scale) * 60).toFixed(1)}′ across
        </div>
        {show.scale && <ScaleBar span={wcs.span} scale={scale} />}
        {show.closeup && (hasSrc || useRgb) && (
          <Loupe center={loupeCenter} span={wcs.span} pixels={manifest.pixels} pred={isDeep ? null : frame.predicted}
            track={frames.map((f) => f.predicted).filter(Boolean)}>
            {useRgb && rgbUrls ? (
              <FrameCanvas rgb={{ ...rgbUrls, gamma }} alt="close-up" />
            ) : (
              <FrameCanvas single={{ url: src, lut, lutName, gamma }} alt="close-up"
                focus={isDiff ? undefined : {
                  ...loupeCenter,
                  r: (LOUPE_ARCMIN / 60 / wcs.span) * 0.6,
                  refUrl: Array.isArray(deep?.image_url) ? deep.image_url[0] : deep?.image_url,
                }} />
            )}
          </Loupe>
        )}
        {hover && (
          <div className="readout">
            {fmtRA(hover.ra)} {fmtDec(hover.dec)}
            {hover.level !== null && !useRgb && (
              <span> · {typeof hover.level === 'number' ? `level ${hover.level}` : 'no data'}</span>
            )}
          </div>
        )}
      </div>

      <div className="controls">
        <button
          onClick={() => setPlaying((p) => !p)}
          disabled={isDeep || n < 2}
          className="play"
          title="Play / Pause (Hotkey: Spacebar)"
        >
          {playing && !isDeep && n > 1 ? '❚❚ Pause' : '▶ Play'}
        </button>
        <button className={`blink ${blink ? 'on' : ''}`} disabled={isDeep || n < 2}
          title="Flip between the first and last visit only: the biggest time gap, so movement is easiest to see"
          onClick={() => { setBlink((b) => !b); setIdx(0); setPlaying(true) }}>
          First ↔ last
        </button>
                <button
          className="step-btn"
          onClick={() => {
            setPlaying(false)
            setIdx((i) => (i - 1 + n) % Math.max(n, 1))
          }}
          disabled={isDeep || n < 2}
          title="Previous epoch (Hotkey: ←)"
        >
          ⏮
        </button>

        <input
          type="range"
          min="0"
          max={Math.max(n - 1, 0)}
          value={idx}
          disabled={isDeep}
          onChange={(e) => {
            setPlaying(false)
            setIdx(Number(e.target.value))
          }}
          aria-label="Visit date timeline"
          title="Drag to scrub through SPHEREx survey timeline"
        />

        <button
          className="step-btn"
          onClick={() => {
            setPlaying(false)
            setIdx((i) => (i + 1) % Math.max(n, 1))
          }}
          disabled={isDeep || n < 2}
          title="Next epoch (Hotkey: →)"
        >
          ⏭
        </button>

        <label>
          Speed
          <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
            {[0.5, 1, 2, 4, 8].map((v) => (
              <option key={v} value={v}>
                {v}x ({v} fps)
              </option>
            ))}
          </select>
        </label>

        <label>
          Zoom
          <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
            {[1, 1.5, 2, 3, 4].map((v) => (
              <option key={v} value={v}>
                {v}×
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="controls look">
        <label>
          Colour
          {isDiff ? (
            <select value={dmap} onChange={(e) => setDmap(e.target.value)}>
              {Object.entries(DIFF_COLORMAPS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          ) : (
            <select value={cmap} onChange={(e) => setCmap(e.target.value)}>
              {Object.entries(COLORMAPS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
              <option value="rgb" disabled={!rgbAllowed}>
                3-colour infrared{rgbAllowed ? '' : ' (choose All)'}
              </option>
            </select>
          )}
        </label>
        <label>
          Contrast
          <select value={stretch} onChange={(e) => setStretch(e.target.value)}>
            {Object.entries(STRETCHES).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <div className="chips" role="group" aria-label="Overlays">
          {OVERLAYS.map(([k, label, color]) => {
            const missing =
              (k === 'gaia' && !catalogs?.gaia) || (k === 'allwise' && !catalogs?.allwise)
            return (
              <button
                key={k}
                className={`chip ${show[k] && !missing ? 'on' : ''}`}
                disabled={missing}
                title={
                  missing ? 'No catalogue for this target yet (run science/fetch_catalogs.py)' : ''
                }
                onClick={() => setShow((s) => ({ ...s, [k]: !s[k] }))}
              >
                <i style={{ background: color }} />
                {label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="dates">
        {frames.map((f, i) => (
          <button
            key={f.image_url || i}
            className={i === idx && !isDeep ? 'on' : ''}
            onClick={() => {
              setPlaying(false)
              setIdx(i)
            }}
          >
            {f.date}
          </button>
        ))}
      </div>
    </div>
  )
}
