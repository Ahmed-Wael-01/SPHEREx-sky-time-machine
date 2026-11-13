import { useCallback, useEffect, useMemo, useState } from 'react'
import SkyForm from './components/SkyForm.jsx'
import Player from './components/Player.jsx'
import MetaPanel from './components/MetaPanel.jsx'
import SpectrumPlot from './components/SpectrumPlot.jsx'
import { getFrames, getSpectrum, NotFound } from './lib/api.js'
import { readUrl, writeUrl } from './lib/urlState.js'
import { TARGETS, MOCK_TARGET, DEFAULT_TARGET } from './lib/targets.js'

// Nominal SPHEREx band edges (um); real ranges come from the manifest when WCS-WAVE was readable.
const NOMINAL_WL = { 1: [0.75, 1.11], 2: [1.11, 1.64], 3: [1.64, 2.42], 4: [2.42, 3.82], 5: [3.82, 4.42], 6: [4.42, 5.0] }

function initialQuery() {
  const u = readUrl()
  const t = [...TARGETS, MOCK_TARGET].find((x) => x.slug === u.target)
  if (t) return { target: t.slug, ra: t.ra, dec: t.dec, fov: u.fov ?? t.fov }
  if (u.ra !== undefined && u.dec !== undefined) return { ra: u.ra, dec: u.dec, fov: u.fov ?? 0.2 }
  const d = [...TARGETS, MOCK_TARGET].find((x) => x.slug === DEFAULT_TARGET)
  return { target: d.slug, ra: d.ra, dec: d.dec, fov: d.fov }
}

export default function App() {
  const url = useMemo(readUrl, [])
  const [query, setQuery] = useState(initialQuery)
  const [manifest, setManifest] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [det, setDet] = useState(url.det ?? 0)
  const [mode, setMode] = useState(url.mode ?? 'frames') // frames | diff | deep
  const [idx, setIdx] = useState(url.t ?? 0)
  const [spectrum, setSpectrum] = useState(null)
  const [clicked, setClicked] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setSpectrum(null)
    setClicked(null)
    getFrames(query)
      .then((m) => {
        if (cancelled) return
        setManifest(m)
        const dets = [0, ...(m.detectors || [])]
        setDet((d) => (dets.includes(d) ? d : 0))
      })
      .catch((e) => {
        if (cancelled) return
        setManifest(null)
        setError(e instanceof NotFound ? e.message : `Could not load frames: ${e.message}`)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [query])

  const frames = useMemo(
    () => (manifest?.visits || []).filter((v) => v.detector === det).sort((a, b) => a.mjd - b.mjd),
    [manifest, det],
  )
  const deep = useMemo(() => (manifest?.deep || []).find((d) => d.detector === det), [manifest, det])

  useEffect(() => {
    if (idx >= frames.length && frames.length) setIdx(0)
  }, [frames, idx])

  useEffect(() => {
    writeUrl({
      ...(query.target ? { target: query.target } : { ra: +query.ra.toFixed(5), dec: +query.dec.toFixed(5) }),
      fov: query.fov,
      det: det || undefined,
      mode: mode !== 'frames' ? mode : undefined,
      t: idx || undefined,
      embed: url.embed ? 1 : undefined,
    })
  }, [query, det, mode, idx, url.embed])

  const onPick = useCallback(
    async (pos) => {
      setClicked(pos)
      setSpectrum(await getSpectrum({ ra: pos.ra, dec: pos.dec, target: query.target }))
    },
    [query.target],
  )

  const wl = (d) => manifest?.detector_wavelength_um?.[d] || (d ? NOMINAL_WL[d] : [0.75, 5.0])

  return (
    <div className={`app ${url.embed ? 'embed' : ''}`}>
      {!url.embed && (
        <header className="top">
          <div className="brand">
            <span className="logo" aria-hidden>
              <span />
            </span>
            <div>
              <h1>SPHEREx Sky Time Machine</h1>
              <p>Watch a patch of the infrared sky change over time · Null Point</p>
            </div>
          </div>
        </header>
      )}

      {!url.embed && <SkyForm query={query} onSubmit={(q) => { setIdx(0); setQuery(q) }} />}

      <main className="stage">
        <section className="viewer">
          {manifest?.target === 'mock' && <div className="banner">Synthetic test data, not real SPHEREx images</div>}
          <div className="toolbar">
            <div className="seg" role="group" aria-label="Detector">
              {[0, ...(manifest?.detectors || [1, 2, 3, 4, 5, 6])].map((d) => (
                <button key={d} className={d === det ? 'on' : ''} onClick={() => setDet(d)}
                  title={`${wl(d)[0]}–${wl(d)[1]} µm`}>
                  {d === 0 ? 'All' : `D${d}`}
                  <small>{wl(d)[0].toFixed(2)}–{wl(d)[1].toFixed(2)} µm</small>
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label="Mode">
              {[['frames', 'Frames'], ['diff', 'Difference'], ['deep', 'Sum (deep)']].map(([k, label]) => (
                <button key={k} className={k === mode ? 'on' : ''} onClick={() => setMode(k)}>{label}</button>
              ))}
            </div>
          </div>

          {loading && <div className="empty">Loading frames…</div>}
          {!loading && error && <div className="empty error">{error}</div>}
          {!loading && manifest && (
            <Player manifest={manifest} frames={frames} deep={deep} mode={mode} idx={idx} setIdx={setIdx}
              onPick={onPick} clicked={clicked} />
          )}
        </section>

        <aside className="side">
          <MetaPanel manifest={manifest} frame={mode === 'deep' ? deep : frames[idx]} mode={mode} det={det} wl={wl(det)} />
          {clicked && <SpectrumPlot data={spectrum} pos={clicked} />}
        </aside>
      </main>

      {!url.embed && (
        <footer className="foot">
          Data: NASA SPHEREx via NASA/IPAC IRSA. Built for NASA Space Apps 2026, “Planet X and SPHEREx”.
          We don’t claim to find Planet X; this tool gives anyone the means to look.
        </footer>
      )}
    </div>
  )
}
