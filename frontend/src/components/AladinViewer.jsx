import { useEffect, useRef, useState } from 'react'
import A from 'aladin-lite'

// NASA / IPAC IRSA official high-speed HiPS tile mirrors (with CORS enabled)
const HIPS_SURVEYS = {
  allwise: {
    label: 'AllWISE Infrared (NASA IRSA)',
    url: 'https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/RGB-W4-W2-W1',
  },
  dss2: {
    label: 'DSS2 Optical Color (NASA IRSA)',
    url: 'https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color',
  },
  twomass: {
    label: '2MASS Near-Infrared (NASA IRSA)',
    url: 'https://irsa.ipac.caltech.edu/data/hips/CDS/2MASS/Color',
  },
}

export default function AladinViewer({ ra, dec, fov = 0.2, targetName = '', clicked = null }) {
  const containerRef = useRef(null)
  const aladinInstance = useRef(null)
  const gaiaCatRef = useRef(null)
  const wiseCatRef = useRef(null)
  const clickedMarkerCat = useRef(null)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [showGaia, setShowGaia] = useState(true)
  const [showWise, setShowWise] = useState(true)
  const [surveyKey, setSurveyKey] = useState('allwise')

  useEffect(() => {
    let active = true

    A.init
      .then(() => {
        if (!active || !containerRef.current) return

        if (!aladinInstance.current) {
          try {
            const initialSurveyUrl = HIPS_SURVEYS[surveyKey].url

            const aladin = A.aladin(containerRef.current, {
              survey: initialSurveyUrl,
              fov: fov,
              target: `${ra} ${dec}`,
              cooFrame: 'J2000',
              showReticle: true,
              showLayersControl: false,
              showZoomControl: true,
              showFullscreenControl: false,
            })
            aladinInstance.current = aladin

            // Overlay Gaia DR3 Catalog from VizieR
            try {
              const gaia = A.catalogFromVizieR('I/355/gaiadr3', `${ra} ${dec}`, fov / 2, {
                onClick: 'showPopup',
                name: 'Gaia DR3 (Proper Motions)',
                color: '#34d399',
                shape: 'circle',
                sourceSize: 8,
              })
              gaiaCatRef.current = gaia
              aladin.addCatalog(gaia)
            } catch (catErr) {
              console.warn('Could not load Gaia DR3 catalog:', catErr)
            }

            // Overlay AllWISE Catalog from VizieR
            try {
              const wise = A.catalogFromVizieR('II/328/allwise', `${ra} ${dec}`, fov / 2, {
                onClick: 'showPopup',
                name: 'AllWISE Catalog',
                color: '#f43f5e',
                shape: 'square',
                sourceSize: 7,
              })
              wiseCatRef.current = wise
              aladin.addCatalog(wise)
            } catch (catErr) {
              console.warn('Could not load AllWISE catalog:', catErr)
            }

            setLoading(false)
          } catch (err) {
            console.error('Aladin instantiate error:', err)
            setLoadError(`Initialization error: ${err.message || err}`)
            setLoading(false)
          }
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
          console.error('Aladin init error:', err)
          setLoadError(typeof err === 'string' ? err : err.message || 'WebGL2 error')
          setLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [ra, dec, fov])

  // Automatically fly to and highlight any object clicked in the SPHEREx player
  useEffect(() => {
    if (!clicked || !aladinInstance.current) return
    try {
      aladinInstance.current.gotoRaDec(clicked.ra, clicked.dec)

      // Remove previous selection marker layer if present
      if (clickedMarkerCat.current) {
        try {
          aladinInstance.current.removeLayers([clickedMarkerCat.current])
        } catch (_) {}
      }

      // Add prominent highlighted marker for user's selected SPHEREx target
      const cat = A.catalog({
        name: 'Targeted SPHEREx Object',
        color: '#ffb020',
        shape: 'cross',
        sourceSize: 18,
        onClick: 'showPopup',
      })
      const src = A.source(clicked.ra, clicked.dec, {
        popupTitle: 'Targeted SPHEREx Object',
        popupDesc: `RA: ${clicked.ra.toFixed(5)}° · Dec: ${clicked.dec.toFixed(5)}°`,
      })
      cat.addSources([src])
      aladinInstance.current.addCatalog(cat)
      clickedMarkerCat.current = cat
    } catch (e) {
      console.warn('Error syncing clicked target to Aladin:', e)
    }
  }, [clicked])

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

  // Switch Base Survey with NASA IRSA HiPS mirrors
  const handleSurveyChange = (e) => {
    const key = e.target.value
    setSurveyKey(key)
    const targetUrl = HIPS_SURVEYS[key]?.url
    if (aladinInstance.current && targetUrl) {
      aladinInstance.current.setImageSurvey(targetUrl)
    }
  }

  return (
    <div className="aladin-card">
      <div className="aladin-toolbar">
        <div className="survey-select">
          <label>Survey: </label>
          <select value={surveyKey} onChange={handleSurveyChange}>
            {Object.entries(HIPS_SURVEYS).map(([k, s]) => (
              <option key={k} value={k}>
                {s.label}
              </option>
            ))}
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
        {loading && !loadError && (
          <div className="aladin-loader">Connecting to NASA IRSA HiPS Archive…</div>
        )}
        {loadError && (
          <div className="aladin-loader error">
            <p>⚠️ {loadError}</p>
          </div>
        )}
        <div ref={containerRef} className="aladin-viewport" />
      </div>

      <div className="aladin-legend">
        <span>Target: <b>{targetName || `${ra.toFixed(4)}, ${dec.toFixed(4)}`}</b> (FoV: {fov}°)</span>
        <span>Astrometry: <span style={{ color: '#34d399' }}>● Gaia DR3</span> · <span style={{ color: '#f43f5e' }}>■ AllWISE</span></span>
      </div>
    </div>
  )
}
