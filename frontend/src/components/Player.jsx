import { useEffect, useRef, useState } from 'react'

export default function Player({
  manifest,
  frames,
  deep,
  mode,
  setMode,
  idx,
  setIdx,
  onPick,
  clicked,
}) {
  const [playing, setPlaying] = useState(true)
  const [fps, setFps] = useState(2)
  const [zoom, setZoom] = useState(1)
  const [marker, setMarker] = useState(true)
  const [isBlinking, setIsBlinking] = useState(false)
  const boxRef = useRef(null)

  const isDeep = mode === 'deep'
  const frame = isDeep ? deep : frames[idx]
  const src = frame ? (mode === 'diff' ? frame.diff_url : frame.image_url) : null
  const n = frames.length

  // Preload every frame of the current detector/mode to prevent flicker
  useEffect(() => {
    frames.forEach((f) => {
      const u1 = f.image_url
      const u2 = f.diff_url
      if (u1) new Image().src = u1
      if (u2) new Image().src = u2
    })
  }, [frames])

  // Playback loop
  useEffect(() => {
    if (!playing || isDeep || n < 2) return
    const id = setInterval(() => setIdx((i) => (i + 1) % n), 1000 / fps)
    return () => clearInterval(id)
  }, [playing, fps, n, isDeep, setIdx])

  // Astronomical hotkeys: Space, Arrows, 'B' (Blink), 'D' (Diff mode toggle)
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return

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
        // Blink comparator: alternate between current frame and previous frame
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

  const fieldDeg = (manifest.pixels * manifest.pixel_scale_arcsec) / 3600

  const click = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    const fx = (e.clientX - r.left) / r.width
    const fy = (e.clientY - r.top) / r.height
    // small-field tangent plane: north up, east left
    const dec = manifest.dec + (0.5 - fy) * fieldDeg
    const ra = manifest.ra - ((fx - 0.5) * fieldDeg) / Math.cos((manifest.dec * Math.PI) / 180)
    onPick({ ra: (ra + 360) % 360, dec, fx, fy })
  }

  const pred = !isDeep && frame?.predicted

  if (!frame) return <div className="empty">No frames available for this detector.</div>

  return (
    <div className="player">
      <div className={`frame-box ${isBlinking ? 'blink-active' : ''}`} ref={boxRef}>
        <div
          className="frame-inner"
          style={{ transform: `scale(${zoom})` }}
          onClick={click}
          title="Click to inspect 102-band infrared spectrum & light curve at this position"
        >
          {src ? (
            <img src={src} alt={`SPHEREx frame ${frame.date || 'deep stack'}`} draggable={false} />
          ) : (
            <div className="empty">No difference image (only one visit available)</div>
          )}

          {/* Predicted target position calculated from known proper motion */}
          {marker && pred && (
            <span
              className="marker"
              style={{ left: `${pred.fx * 100}%`, top: `${pred.fy * 100}%` }}
              title={`Predicted proper motion position for epoch: ${frame.date}`}
            />
          )}

          {/* User inspection target reticle */}
          {clicked && (
            <span
              className="pick"
              style={{ left: `${clicked.fx * 100}%`, top: `${clicked.fy * 100}%` }}
              title="Selected aperture for spectral extraction"
            />
          )}
        </div>

        <div className="stamp">
          {isDeep
            ? `Deep Stack Sum · ${frame.n_exposures} exposures`
            : `${frame.date} (MJD ${frame.mjd ? frame.mjd.toFixed(1) : '—'}) · visit ${idx + 1}/${n}`}
        </div>
        <div className="compass" aria-hidden>N ↑ · E ← · 6.15″/px</div>
        <div className="click-hint">Click object to view 102-band Spectrum & Light Curve</div>
      </div>

      <div className="controls">
        <button
          onClick={() => setPlaying((p) => !p)}
          disabled={isDeep || n < 2}
          className="play"
          title="Play / Pause (Hotkey: Spacebar)"
        >
          {playing ? '❚❚ Pause' : '▶ Play'}
        </button>

        <button
          className="step-btn"
          onClick={() => { setPlaying(false); setIdx((i) => (i - 1 + n) % Math.max(n, 1)) }}
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
          onClick={() => { setPlaying(false); setIdx((i) => (i + 1) % Math.max(n, 1)) }}
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

        <label className="check">
          <input
            type="checkbox"
            checked={marker}
            onChange={(e) => setMarker(e.target.checked)}
          />{' '}
          Track Motion
        </label>
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
