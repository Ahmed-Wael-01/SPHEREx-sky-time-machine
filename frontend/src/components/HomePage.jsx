import React from 'react'
import { TARGETS, MOCK_TARGET } from '../lib/targets.js'

export default function HomePage({ onLaunch, onSelectTarget }) {
  return (
    <div className="home-container">
      {/* Hero Section */}
      <section className="home-hero">
        <div className="home-hero-badge">
          <span className="hero-pulse" />
          <span>NASA Space Apps Cairo 2026 · Challenge: Planet X and SPHEREx · Team Null Point</span>
        </div>

        <div className="home-hero-content">
          <h1 className="home-title">
            SPHEREx Sky <span className="title-highlight">Time Machine</span>
          </h1>
          <p className="home-subtitle">
            An advanced multi-epoch infrared time machine and 102-channel spectrophotometry platform.
            Uncover cold moving substellar objects, Planet X candidates, extreme variable stars, and cosmic transients across SPHEREx all-sky survey passes.
          </p>

          <div className="home-cta-group">
            <button
              type="button"
              className="cta-btn primary"
              onClick={() => onLaunch()}
            >
              🚀 Launch Sky Time Machine
            </button>
            <button
              type="button"
              className="cta-btn secondary"
              onClick={() => onSelectTarget ? onSelectTarget(TARGETS[0]) : onLaunch('wise0855')}
            >
              🪐 Inspect WISE 0855 (Planet X Analog)
            </button>
            <button
              type="button"
              className="cta-btn outline"
              onClick={() => onSelectTarget ? onSelectTarget(MOCK_TARGET) : onLaunch('mock')}
            >
              🧪 Synthetic Offline Test
            </button>
          </div>
        </div>

        {/* Live Metrics Row */}
        <div className="home-stats-grid">
          <div className="stat-card">
            <div className="stat-num">102</div>
            <div className="stat-label">Spectral Bands</div>
            <div className="stat-sub">0.75 – 5.0 µm continuous IR</div>
          </div>
          <div className="stat-card">
            <div className="stat-num">6</div>
            <div className="stat-label">LVF Detectors</div>
            <div className="stat-sub">Linear Variable Filter mosaic</div>
          </div>
          <div className="stat-card">
            <div className="stat-num">4+</div>
            <div className="stat-label">Survey Passes</div>
            <div className="stat-sub">Multi-epoch flip-book & difference</div>
          </div>
          <div className="stat-card">
            <div className="stat-num">&lt; 0.8″</div>
            <div className="stat-label">Astrometric Match</div>
            <div className="stat-sub">Gaia DR3, AllWISE & SIMBAD</div>
          </div>
        </div>
      </section>

      {/* What the Platform Does Section */}
      <section className="home-features">
        <div className="section-head">
          <span className="section-tag">CAPABILITIES & SCIENCE</span>
          <h2>What Does the SPHEREx Sky Time Machine Do?</h2>
          <p>
            Bridging raw NASA/IPAC infrared survey archives with interactive citizen science and astronomical research.
          </p>
        </div>

        <div className="feature-grid">
          <div className="feature-card">
            <div className="feature-icon">🎞️</div>
            <h3>Multi-Epoch Flip-Book & Difference Engine</h3>
            <p>
              Compare consecutive 6-month sky passes with rapid frame switching, adjustable playback speed (0.5x–8x),
              blink comparator (<code>B</code>), and difference imaging (<code>D</code>) to immediately isolate high-proper-motion candidates.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🔬</div>
            <h3>102-Band Infrared Spectrophotometry</h3>
            <p>
              Click any point on the sky to extract calibrated 102-channel spectral energy distributions (SEDs),
              complete with error bars, flagged artifact detection, and atmospheric molecular markers (H₂O, CH₄, CO₂, CO).
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">📈</div>
            <h3>Multi-Epoch Light Curves</h3>
            <p>
              Examine flux variations over time across multiple sky passes to detect stellar variability,
              occultations, young stellar dust clearing events, and transient infrared flares.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🌐</div>
            <h3>Multi-Catalog Overlays & Live SIMBAD</h3>
            <p>
              Direct astrometric integration with <b>Gaia DR3</b> (with proper motion propagation) and <b>AllWISE</b> sources.
              Integrated live SIMBAD query automatically identifies cataloged objects or flags uncataloged movers.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🎨</div>
            <h3>Dynamic Colormaps & 3-Colour IR</h3>
            <p>
              Customizable false-color visualizations: Heat, Viridis, Inferno, Null Point Blue, and Blue-Red Difference,
              plus an authentic <b>3-Colour Infrared Composite</b> (B: 0.75–1.6 µm, G: 1.6–3.8 µm, R: 3.8–5.0 µm).
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🔍</div>
            <h3>Live Field-of-View Cropping & Scale</h3>
            <p>
              Real-time interactive Field-of-View (FoV) slider dynamically cropping down to arcminute scales,
              backed by an adaptive coordinate grid and calibrated on-sky scale bar.
            </p>
          </div>
        </div>
      </section>

      {/* Curated NASA Targets Showcase */}
      <section className="home-targets-showcase">
        <div className="section-head">
          <span className="section-tag">CURATED NASA BENCHMARKS</span>
          <h2>Explore Key Astronomical Targets</h2>
          <p>
            Hand-picked targets demonstrating SPHEREx capabilities for Planet X analogs, fastest proper motions, and extreme variables.
          </p>
        </div>

        <div className="target-cards-grid">
          {TARGETS.map((t) => (
            <div key={t.slug} className="target-showcase-card">
              <div className="target-card-top">
                <span className="target-kind-tag">{t.tag}</span>
                <span className="target-coords-text">{t.ra.toFixed(2)}°, {t.dec.toFixed(2)}°</span>
              </div>
              <h3>{t.label}</h3>
              <p className="target-blurb-text">{t.blurb}</p>
              {t.tip && (
                <div className="target-tip-box">
                  💡 <b>Observer Tip:</b> {t.tip}
                </div>
              )}
              <button
                type="button"
                className="target-explore-btn"
                onClick={() => onSelectTarget ? onSelectTarget(t) : onLaunch(t.slug)}
              >
                Inspect in Time Machine →
              </button>
            </div>
          ))}

          {/* Synthetic Offline Smoke Test Card */}
          <div className="target-showcase-card mock-card">
            <div className="target-card-top">
              <span className="target-kind-tag mock">Developer Test</span>
              <span className="target-coords-text">Offline Scaffolding</span>
            </div>
            <h3>Synthetic Test Field</h3>
            <p className="target-blurb-text">{MOCK_TARGET.blurb}</p>
            <div className="target-tip-box">
              ⚙️ <b>Development Scaffolding:</b> {MOCK_TARGET.tip}
            </div>
            <button
              type="button"
              className="target-explore-btn"
              onClick={() => onSelectTarget ? onSelectTarget(MOCK_TARGET) : onLaunch('mock')}
            >
              Run Synthetic Smoke Test →
            </button>
          </div>
        </div>
      </section>

      {/* Challenge & Mission Background Section */}
      <section className="home-mission-section">
        <div className="mission-content">
          <span className="section-tag">THE CHALLENGE</span>
          <h2>Planet X and SPHEREx: Solving the Challenge</h2>
          <p>
            NASA’s SPHEREx mission maps the entire celestial sphere every six months in 102 near-infrared bands.
            The sheer volume of spectroscopic and temporal data presents a challenge: how can researchers and citizen scientists
            reliably distinguish genuine moving solar system objects (like the hypothesized Planet X / Planet Nine)
            and variable stars from detector artifacts, dichroic boundaries, and cosmic ray transients?
          </p>
          <p>
            <strong>Team Null Point</strong> created the <strong>SPHEREx Sky Time Machine</strong> to provide an intuitive,
            scientifically rigorous environment: combining pixel-level difference imaging, dynamic colormaps, 102-band spectrophotometry,
            and automated Gaia/WISE/SIMBAD cross-matching to empower astronomers and the public alike.
          </p>
          <div className="mission-actions">
            <button
              type="button"
              className="cta-btn primary"
              onClick={() => onLaunch()}
            >
              Launch Interactive Time Machine 🚀
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
