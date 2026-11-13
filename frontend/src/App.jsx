import { useCallback, useEffect, useMemo, useState } from 'react'
import SkyForm from './components/SkyForm.jsx'
import Player from './components/Player.jsx'
import MetaPanel from './components/MetaPanel.jsx'
import SpectrumPlot from './components/SpectrumPlot.jsx'
import ObjectDetailModal from './components/ObjectDetailModal.jsx'
import AladinViewer from './components/AladinViewer.jsx'
import { getFrames, getSpectrum, NotFound } from './lib/api.js'
import { readUrl, writeUrl } from './lib/urlState.js'
import { TARGETS, MOCK_TARGET, DEFAULT_TARGET } from './lib/targets.js'

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
  const [query, setQuery] = useState(initialQuery)
  const [manifest, setManifest] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [det, setDet] = useState(url.det ?? 0)
  const [mode, setMode] = useState(url.mode ?? 'frames') // frames | diff | deep
  const [viewTab, setViewTab] = useState('player') // 'player' | 'aladin' | 'split'
  const [idx, setIdx] = useState(url.t ?? 0)
  const [spectrum, setSpectrum] = useState(null)
  const [clicked, setClicked] = useState(null)
  const [showModal, setShowModal] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setSpectrum(null)
    setClicked(null)
    setShowModal(false)

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
      const spec = await getSpectrum({ ra: pos.ra, dec: pos.dec, target: query.target })
      setSpectrum(spec)
      setShowModal(true)
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
              <h1>SPHEREx Sky Time Machine youssef</h1>
              <p>NASA Space Apps Cairo 2026 · Challenge: Planet X and SPHEREx · Team Null Point</p>
            </div>
          </div>
          <div className="header-badges">
            <span className="team-badge">Team Null Point</span>
          </div>
        </header>
      )}

      {!url.embed && (
        <SkyForm
          query={query}
          onSubmit={(q) => {
            setIdx(0)
            setQuery(q)
          }}
        />
      )}

      {/* Main View Switching Navigation */}
      <div className="view-switcher">
        <div className="view-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={viewTab === 'player'}
            className={viewTab === 'player' ? 'vtab active' : 'vtab'}
            onClick={() => setViewTab('player')}
          >
            🎬 SPHEREx Time Machine
          </button>
          <button
            role="tab"
            aria-selected={viewTab === 'aladin'}
            className={viewTab === 'aladin' ? 'vtab active' : 'vtab'}
            onClick={() => setViewTab('aladin')}
          >
            🌌 Aladin Lite Reference (Gaia DR3 & WISE)
          </button>
          <button
            role="tab"
            aria-selected={viewTab === 'split'}
            className={viewTab === 'split' ? 'vtab active' : 'vtab'}
            onClick={() => setViewTab('split')}
          >
            ◫ Dual Comparison (Split View)
          </button>
        </div>
      </div>

      <main className={`stage ${viewTab === 'split' ? 'split-layout' : ''}`}>
        <section className="viewer">
          {manifest?.target === 'mock' && (
            <div className="banner">
              Synthetic test data: Offline smoke test scaffolding, not real SPHEREx flight data.
            </div>
          )}

          {/* Detector & Mode Controls for SPHEREx */}
          {(viewTab === 'player' || viewTab === 'split') && (
            <div className="toolbar">
              <div className="seg" role="group" aria-label="Detector Bandpass">
                {[0, ...(manifest?.detectors || [1, 2, 3, 4, 5, 6])].map((d) => (
                  <button
                    key={d}
                    className={d === det ? 'on' : ''}
                    onClick={() => setDet(d)}
                    title={`Detector ${d}: ${wl(d)[0]}–${wl(d)[1]} µm`}
                  >
                    {d === 0 ? 'All Detectors' : `D${d}`}
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
          )}

          {loading && <div className="empty">Connecting to NASA/IPAC IRSA archive…</div>}
          {!loading && error && <div className="empty error">{error}</div>}

          {/* SPHEREx Time Machine Player */}
          {!loading && manifest && (viewTab === 'player' || viewTab === 'split') && (
            <Player
              manifest={manifest}
              frames={frames}
              deep={deep}
              mode={mode}
              setMode={setMode}
              idx={idx}
              setIdx={setIdx}
              onPick={onPick}
              clicked={clicked}
            />
          )}

          {/* Aladin Lite Reference Sky Map */}
          {(viewTab === 'aladin' || viewTab === 'split') && (
            <AladinViewer
              ra={query.ra ?? manifest?.ra ?? 133.795}
              dec={query.dec ?? manifest?.dec ?? -7.245}
              fov={query.fov ?? manifest?.fov ?? 0.2}
              targetName={manifest?.name || query.target}
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
            <div className="spectrum-side-card">
              <SpectrumPlot data={spectrum} pos={clicked} />
              <button
                type="button"
                className="expand-spec-btn"
                onClick={() => setShowModal(true)}
              >
                🔬 Full 102-Band & Light Curve Analysis
              </button>
            </div>
          )}
        </aside>
      </main>

      {/* Full Analysis Modal */}
      {showModal && clicked && (
        <ObjectDetailModal
          pos={clicked}
          data={spectrum}
          onClose={() => setShowModal(false)}
        />
      )}

      {!url.embed && (
        <footer className="foot">
          Data source: NASA SPHEREx Infrared Science Archive (IRSA) · Gaia DR3 & AllWISE via CDS Strasbourg VizieR.
          Built for NASA Space Apps 2026, “Planet X and SPHEREx”.
        </footer>
      )}
    </div>
  )
}
