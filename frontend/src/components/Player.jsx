import { useEffect, useRef, useState } from 'react'

export default function Player({ manifest, frames, deep, mode, idx, setIdx, onPick, clicked }) {
  const [playing, setPlaying] = useState(true)
  const [fps, setFps] = useState(2)
  const [zoom, setZoom] = useState(1)
  const [marker, setMarker] = useState(true)
  const boxRef = useRef(null)

  const isDeep = mode === 'deep'
  const frame = isDeep ? deep : frames[idx]
  const src = frame ? (mode === 'diff' ? frame.diff_url : frame.image_url) : null
  const n = frames.length

  // preload every frame of the current detector/mode so playback doesn't flicker
  useEffect(() => {
    frames.forEach((f) => {
      const u = mode === 'diff' ? f.diff_url : f.image_url
      if (u) new Image().src = u
    })
  }, [frames, mode])

  useEffect(() => {
    if (!playing || isDeep || n < 2) return
    const id = setInterval(() => setIdx((i) => (i + 1) % n), 1000 / fps)
    return () => clearInterval(id)
  }, [playing, fps, n, isDeep, setIdx])

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT') return
      if (e.code === 'Space') { e.preventDefault(); setPlaying((p) => !p) }
      if (e.code === 'ArrowRight') { setPlaying(false); setIdx((i) => (i + 1) % Math.max(n, 1)) }
      if (e.code === 'ArrowLeft') { setPlaying(false); setIdx((i) => (i - 1 + n) % Math.max(n, 1)) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [n, setIdx])

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

  if (!frame) return <div className="empty">No frames for this detector.</div>

  return (
    <div className="player">
      <div className="frame-box" ref={boxRef}>
        <div className="frame-inner" style={{ transform: `scale(${zoom})` }} onClick={click}>
          {src ? <img src={src} alt={`SPHEREx frame ${frame.date || 'deep stack'}`} draggable={false} />
            : <div className="empty">No difference image (only one visit)</div>}
          {marker && pred && (
            <span className="marker" style={{ left: `${pred.fx * 100}%`, top: `${pred.fy * 100}%` }}
              title="Predicted position of the target on this date (from proper motion)" />
          )}
          {clicked && <span className="pick" style={{ left: `${clicked.fx * 100}%`, top: `${clicked.fy * 100}%` }} />}
        </div>
        <div className="stamp">
          {isDeep ? `Deep stack · ${frame.n_exposures} exposures` : `${frame.date} · visit ${idx + 1}/${n}`}
        </div>
        <div className="compass" aria-hidden>N ↑ · E ←</div>
      </div>

      <div className="controls">
        <button onClick={() => setPlaying((p) => !p)} disabled={isDeep || n < 2} className="play">
          {playing ? 'Pause' : 'Play'}
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
        <label className="check">
          <input type="checkbox" checked={marker} onChange={(e) => setMarker(e.target.checked)} /> Predicted position
        </label>
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
