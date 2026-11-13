import { useEffect, useRef, useState } from 'react'

function loadAladinScript() {
  return new Promise((resolve, reject) => {
    if (window.A && window.A.aladin) return resolve(window.A)

    const existingScript = document.getElementById('aladin-script')
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve(window.A))
      return
    }

    const script = document.createElement('script')
    script.id = 'aladin-script'
    script.src = 'https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js'
    script.async = true
    script.onload = () => resolve(window.A)
    script.onerror = () => reject(new Error('Failed to load Aladin Lite library from CDS Strasbourg'))
    document.head.appendChild(script)
  })
}

export default function AladinViewer({ ra, dec, fov = 0.2, targetName = '' }) {
  const containerRef = useRef(null)
  const aladinInstance = useRef(null)
  const gaiaCatRef = useRef(null)
  const wiseCatRef = useRef(null)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [showGaia, setShowGaia] = useState(true)
  const [showWise, setShowWise] = useState(true)
  const [survey, setSurvey] = useState('P/allWISE/color')

  useEffect(() => {
    let active = true

    loadAladinScript()
      .then((A) => {
        if (!active || !containerRef.current) return

        if (!aladinInstance.current) {
          A.init.then(() => {
            if (!active || !containerRef.current) return
            try {
              const aladin = A.aladin(containerRef.current, {
                survey: survey,
                fov: fov,
                target: `${ra} ${dec}`,
                cooFrame: 'J2000',
                showReticle: true,
                showLayersControl: false,
                showZoomControl: true,
                showFullscreenControl: false,
              })
              aladinInstance.current = aladin

              // Overlay Gaia DR3 Catalog
              const gaia = A.catalogFromVizieR('I/355/gaiadr3', `${ra} ${dec}`, fov / 2, {
                onClick: 'showPopup',
                name: 'Gaia DR3 (Proper Motions)',
                color: '#34d399',
                shape: 'circle',
                sourceSize: 8,
              })
              gaiaCatRef.current = gaia
              aladin.addCatalog(gaia)

              // Overlay AllWISE Catalog
              const wise = A.catalogFromVizieR('II/328/allwise', `${ra} ${dec}`, fov / 2, {
                onClick: 'showPopup',
                name: 'AllWISE Catalog',
                color: '#f43f5e',
                shape: 'square',
                sourceSize: 7,
              })
              wiseCatRef.current = wise
              aladin.addCatalog(wise)

              setLoading(false)
            } catch (err) {
              console.warn('Aladin init error:', err)
              setLoading(false)
            }
          })
        } else {
          // Re-center coordinates and FoV if target changes
          try {
            aladinInstance.current.gotoRaDec(ra, dec)
            aladinInstance.current.setFoV(fov)
          } catch (e) {
            console.warn('Aladin update position error:', e)
          }
        }
      })
      .catch((err) => {
        if (active) {
          setLoadError(err.message)
          setLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [ra, dec, fov])

  // Toggle Gaia DR3 Overlay
  const toggleGaia = () => {
    if (!gaiaCatRef.current) return
    const next = !showGaia
    setShowGaia(next)
    gaiaCatRef.current.reportChange({ visible: next })
  }

  // Toggle AllWISE Overlay
  const toggleWise = () => {
    if (!wiseCatRef.current) return
    const next = !showWise
    setShowWise(next)
    wiseCatRef.current.reportChange({ visible: next })
  }

  // Switch Base Survey
  const handleSurveyChange = (e) => {
    const s = e.target.value
    setSurvey(s)
    if (aladinInstance.current) {
      aladinInstance.current.setImageSurvey(s)
    }
  }

  return (
    <div className="aladin-card">
      <div className="aladin-toolbar">
        <div className="survey-select">
          <label>Base Survey: </label>
          <select value={survey} onChange={handleSurveyChange}>
            <option value="P/allWISE/color">AllWISE Infrared (Color)</option>
            <option value="P/DSS2/color">DSS2 Optical (Color)</option>
            <option value="P/2MASS/color">2MASS Near-IR</option>
          </select>
        </div>

        <div className="catalog-toggles">
          <button
            type="button"
            className={showGaia ? 'cat-btn gaia active' : 'cat-btn'}
            onClick={toggleGaia}
            title="Toggle Gaia DR3 astrometric catalogue overlay"
          >
            ● Gaia DR3
          </button>
          <button
            type="button"
            className={showWise ? 'cat-btn wise active' : 'cat-btn'}
            onClick={toggleWise}
            title="Toggle AllWISE catalogue overlay"
          >
            ■ AllWISE
          </button>
        </div>
      </div>

      <div className="aladin-viewport-wrap">
        {loading && <div className="aladin-loader">Loading Aladin Lite v3 from CDS Strasbourg…</div>}
        {loadError && (
          <div className="aladin-loader error">
            Could not connect to CDS Strasbourg: {loadError}. Offline mode active.
          </div>
        )}
        <div ref={containerRef} className="aladin-viewport" />
      </div>

      <div className="aladin-legend">
        <span>Target: <b>{targetName || `${ra.toFixed(4)}, ${dec.toFixed(4)}`}</b> (FoV: {fov}°)</span>
        <span>Astrometric Legend: <span style={{ color: '#34d399' }}>● Gaia DR3</span> · <span style={{ color: '#f43f5e' }}>■ AllWISE</span></span>
      </div>
    </div>
  )
}

