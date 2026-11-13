import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import HomePage from './components/HomePage.jsx'
import SkyForm from './components/SkyForm.jsx'
import Player from './components/Player.jsx'
import MetaPanel from './components/MetaPanel.jsx'
import SpectrumPlot from './components/SpectrumPlot.jsx'
import ObjectDetailModal from './components/ObjectDetailModal.jsx'
import { getFrames, getSpectrum, getSimbad, NotFound } from './lib/api.js'
import { readUrl, writeUrl } from './lib/urlState.js'
import { TARGETS, MOCK_TARGET, DEFAULT_TARGET } from './lib/targets.js'
import { detectorChoices, framesFor, deepFor, wavelengthFor, LONG } from './lib/frames.js'

// Nominal SPHEREx band edges (um); real ranges come from manifest when available
const NOMINAL_WL = {
  1: [0.75, 1.11],
  2: [1.11, 1.64],
  3: [1.64, 2.42],
  4: [2.42, 3.82],
  5: [3.82, 4.42],
  6: [4.42, 5.0],
}

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
  const [view, setView] = useState(() => url.view || (url.target || url.ra ? 'app' : 'home'))
  const [query, setQuery] = useState(initialQuery)
  const [fov, setFov] = useState(() => initialQuery().fov) // field shown; changes live, no refetch
  const keepUrlFov = useRef(url.fov !== undefined) // a shared link may ask for a closer view; honour it once
  const [manifest, setManifest] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  // each target can suggest the view where it shows best (WISE 0855: 4-5 um)
  const defaultDet = (slug) => [...TARGETS, MOCK_TARGET].find((t) => t.slug === slug)?.det ?? 0
  const [det, setDet] = useState(url.det ?? defaultDet(initialQuery().target))
  const [mode, setMode] = useState(url.mode ?? 'frames') // frames | diff | deep
  const [idx, setIdx] = useState(url.t ?? 0)
  const [spectrum, setSpectrum] = useState(null)
  const [clicked, setClicked] = useState(null)
  const [simbadData, setSimbadData] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [catalogs, setCatalogs] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setSpectrum(null)
    setClicked(null)
    setSimbadData(null)
    setShowModal(false)

    getFrames(query)
      .then((m) => {
        if (cancelled) return
        setManifest(m)
        // open on the whole processed photo (the widest view there is), unless the link asked for less
        const span = (m.pixels * m.pixel_scale_arcsec) / 3600
        const keep = keepUrlFov.current // read now: React applies the update later
        keepUrlFov.current = false
        setFov((f) => (keep ? Math.min(f, span) : span))
        setCatalogs(null)
        fetch(`/data/${m.target}/catalogs.json`)
          .then((r) => (r.ok && (r.headers.get('content-type') || '').includes('json') ? r.json() : null))
          .then((c) => !cancelled && setCatalogs(c))
          .catch(() => {})
        const dets = detectorChoices(m)
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
    () => framesFor(manifest, det),
    [manifest, det],
  )
  const deep = useMemo(() => deepFor(manifest, det), [manifest, det])

  useEffect(() => {
    if (idx >= frames.length && frames.length) setIdx(0)
  }, [frames, idx])

  useEffect(() => {
    const handlePopState = () => {
      const u = readUrl()
      setView(u.view)
      if (u.target) {
        const t = [...TARGETS, MOCK_TARGET].find((x) => x.slug === u.target)
        if (t) {
          setFov(u.fov ?? t.fov)
          setQuery({ target: t.slug, ra: t.ra, dec: t.dec, fov: u.fov ?? t.fov })
        }
      } else if (u.ra !== undefined && u.dec !== undefined) {
        setQuery({ ra: u.ra, dec: u.dec, fov: u.fov ?? 0.2 })
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    writeUrl({
      view,
      ...(query.target ? { target: query.target } : { ra: +query.ra.toFixed(5), dec: +query.dec.toFixed(5) }),
      fov: +fov.toFixed(3),
      det: det === defaultDet(query.target) ? undefined : det,
      mode: mode !== 'frames' ? mode : undefined,
      t: idx || undefined,
      embed: url.embed ? 1 : undefined,
    })
  }, [view, query, fov, det, mode, idx, url.embed])

  const handleLaunchTarget = useCallback((target) => {
    const t =
      typeof target === 'string'
        ? [...TARGETS, MOCK_TARGET].find((x) => x.slug === target) || TARGETS[0]
        : target
    setIdx(0)
    setFov(t.fov)
    setDet(t.det ?? 0)
    setQuery({ target: t.slug, ra: t.ra, dec: t.dec, fov: t.fov })
    setView('app')
  }, [])

  const onPick = useCallback(
    async (pos) => {
      setClicked(pos)
      setSimbadData(null)
      getSpectrum({ ra: pos.ra, dec: pos.dec, target: query.target }).then(setSpectrum)
      getSimbad({ ra: pos.ra, dec: pos.dec }).then((r) => setSimbadData(r ?? { match: null, error: 'unavailable' }))
    },
    [query.target],
  )

  // the frames cover a fixed field (set when they were processed); the viewer crops to `fov` inside it
  const bakedSpan = manifest ? (manifest.pixels * manifest.pixel_scale_arcsec) / 3600 : null
  const viewFov = bakedSpan ? Math.min(fov, bakedSpan) : fov

  const wl = (d) => wavelengthFor(manifest, d, NOMINAL_WL)

  return (
    <div className={`app ${url.embed ? 'embed' : ''}`}>
      {!url.embed && (
        <header className="top-nav">
          {/* Brand — click → home */}
          <button type="button" className="nav-brand" onClick={() => setView('home')}>
            <span className="nav-logo" aria-hidden>
              <span />
            </span>
            <div className="nav-brand-text">
              <span className="nav-brand-title">SPHEREx</span>
              <span className="nav-brand-sub">Sky Time Machine</span>
            </div>
          </button>

          {/* Nav links */}
          <nav className="nav-links" aria-label="Main Navigation">
            <button
              type="button"
              className={`nav-link ${view === 'home' ? 'active' : ''}`}
              onClick={() => setView('home')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
              </svg>
              Overview
              {view === 'home' && (
                <motion.span className="nav-active-dot" layoutId="nav-dot" />
              )}
            </button>

            <button
              type="button"
              className={`nav-link ${view === 'app' ? 'active' : ''}`}
              onClick={() => setView('app')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3m-3.5-6.5-2.1 2.1M7.6 16.4l-2.1 2.1m0-13L7.6 7.6m8.8 8.8 2.1 2.1"/>
              </svg>
              Time Machine
              {view === 'app' && (
                <motion.span className="nav-active-dot" layoutId="nav-dot" />
              )}
            </button>
          </nav>

          {/* Launch CTA */}
          <button
            type="button"
            className="nav-cta"
            onClick={() => view === 'home' ? setView('app') : setView('home')}
          >
            {view === 'home' ? '🚀 Launch' : '← Back to Overview'}
          </button>
        </header>
      )}

      {view === 'home' && !url.embed ? (
        <HomePage
          onLaunch={(slug) => {
            if (slug) handleLaunchTarget(slug)
            else setView('app')
          }}
          onSelectTarget={handleLaunchTarget}
        />
      ) : (
        <>
          {!url.embed && (
            <SkyForm
              query={query}
              fov={fov}
              onFov={setFov}
              maxFov={bakedSpan}
              onSubmit={(q) => {
                if (q.fov) setFov(q.fov)
                setIdx(0)
                setQuery(q)
                if (q.target) setDet(defaultDet(q.target))
              }}
            />
          )}

          <main className="stage">
            <section className="viewer">
              {manifest?.target === 'mock' && (
                <div className="banner">
                  Synthetic test data: Offline smoke test scaffolding, not real SPHEREx flight data.
                </div>
              )}

              {/* Detector & Mode Controls for SPHEREx */}
              <div className="toolbar">
                <div className="seg" role="group" aria-label="Detector Bandpass">
                  {detectorChoices(manifest).map((d) => (
                    <button
                      key={d}
                      className={`${d === det ? 'on' : ''} ${d === LONG ? 'long' : ''}`}
                      onClick={() => setDet(d)}
                      title={d === LONG ? 'Detectors 5 + 6 together: where cold brown dwarfs glow' : `Detector ${d}: ${wl(d)[0]}–${wl(d)[1]} µm`}
                    >
                      {d === 0 ? 'All Detectors' : d === LONG ? '4–5 µm' : `D${d}`}
                      <small>{wl(d)[0].toFixed(2)}–{wl(d)[1].toFixed(2)} µm</small>
                    </button>
                  ))}
                </div>
                <div className="seg" role="group" aria-label="Viewing Mode">
                  {[
                    ['frames', 'Visits (Flip-book)'],
                    ['diff', 'Difference (Movers)'],
                    ['deep', 'Sum Stack (Deep)'],
                  ].map(([k, label]) => (
                    <button key={k} className={k === mode ? 'on' : ''} onClick={() => setMode(k)}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {loading && <div className="empty">Connecting to NASA/IPAC IRSA archive…</div>}
              {!loading && error && <div className="empty error">{error}</div>}

              {/* SPHEREx Time Machine Player */}
              {!loading && manifest && (
                <Player
                  manifest={manifest}
                  frames={frames}
                  deep={deep}
                  mode={mode}
                  setMode={setMode}
                  det={det}
                  idx={idx}
                  setIdx={setIdx}
                  onPick={onPick}
                  clicked={clicked}
                  catalogs={catalogs}
                  viewFov={viewFov}
                />
              )}
            </section>

            {/* Sidebar Metadata & Quick Spectrum Preview */}
            <aside className="side">
              <MetaPanel
                manifest={manifest}
                frame={mode === 'deep' ? deep : frames[idx]}
                mode={mode}
                det={det}
                wl={wl(det)}
              />

              {clicked && (
                <div
                  className="spectrum-side-card interactive"
                  onClick={() => setShowModal(true)}
                  title="Click to view full 102-band infrared spectrum & light curve"
                >
                  <SpectrumPlot data={spectrum} pos={clicked} onClick={() => setShowModal(true)} />
                  <button
                    type="button"
                    className="expand-spec-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      setShowModal(true)
                    }}
                  >
                    🔬 Full 102-Band & Light Curve Analysis ↗
                  </button>
                </div>
              )}
            </aside>
          </main>
        </>
      )}

      {/* Full Analysis Modal */}
      {showModal && clicked && (
        <ObjectDetailModal
          pos={clicked}
          data={spectrum}
          simbad={simbadData}
          onClose={() => setShowModal(false)}
        />
      )}

      {!url.embed && (
        <footer className="foot">
          Data source: NASA SPHEREx Infrared Science Archive (IRSA) · SIMBAD Astronomical Database.
          Built for NASA Space Apps 2026, “Planet X and SPHEREx”.
        </footer>
      )}
    </div>
  )
}
