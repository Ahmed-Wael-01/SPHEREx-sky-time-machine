import React, { useEffect, useRef } from 'react'
import { motion } from 'motion/react'
import { TARGETS, MOCK_TARGET } from '../lib/targets.js'

/* ── Animated starfield canvas ── */
function StarField() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let raf

    const resize = () => {
      canvas.width  = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const NUM = 160
    const stars = Array.from({ length: NUM }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: Math.random() * 1.4 + 0.3,
      speed: Math.random() * 0.18 + 0.04,
      alpha: Math.random() * 0.6 + 0.3,
      twinkle: Math.random() * Math.PI * 2,
    }))

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const t = Date.now() / 1000
      stars.forEach(s => {
        s.y += s.speed
        s.twinkle += 0.015
        if (s.y > canvas.height) {
          s.y = 0
          s.x = Math.random() * canvas.width
        }
        const a = s.alpha * (0.7 + 0.3 * Math.sin(s.twinkle))
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(200,215,255,${a})`
        ctx.fill()
      })
      raf = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="hp-starfield" />
}

/* ── Variants ── */
const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.7, ease: 'easeOut' } },
}
const stagger = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.12 } },
}
const fadeItem = {
  hidden: { opacity: 0, y: 20 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.55, ease: 'easeOut' } },
}

/* ── Stats ── */
const STATS = [
  { num: '102',    label: 'Spectral Bands',    sub: '0.75 – 5.0 µm IR' },
  { num: '6',      label: 'LVF Detectors',     sub: 'Linear Variable Filter' },
  { num: '4+',     label: 'Survey Passes',     sub: 'Multi-epoch flip-book' },
  { num: '0.2″',   label: 'Alignment vs Gaia', sub: 'Measured on WISE 0855 field' },
]

/* ── Features ── */
const FEATURES = [
  { icon: '🎞️', title: 'Flip-Book & Diff Engine',     desc: 'Rapid epoch switching with blink comparator and difference imaging.' },
  { icon: '🔬', title: '102-Band Spectrophotometry',   desc: 'Click-to-extract SEDs with molecular markers (H₂O, CH₄, CO₂, CO).' },
  { icon: '🌐', title: 'Gaia / WISE / SIMBAD Overlay', desc: 'Gaia stars moved to each date; AllWISE sources; SIMBAD lookup on click.' },
]

/* ══════════════════════════════════════════════════
   HomePage
══════════════════════════════════════════════════ */
export default function HomePage({ onLaunch, onSelectTarget }) {
  return (
    <div className="hp-root">
      {/* animated starfield */}
      <StarField />

      {/* ── glowing orb (Null Point singularity) ── */}
      <motion.div
        className="hp-orb"
        animate={{ scale: [1, 1.10, 1], opacity: [0.55, 0.85, 0.55] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* ── orbital ring SVG ── */}
      <motion.svg
        className="hp-orbital"
        viewBox="0 0 400 400"
        animate={{ rotate: 360 }}
        transition={{ duration: 28, repeat: Infinity, ease: 'linear' }}
      >
        <ellipse cx="200" cy="200" rx="180" ry="60"
          stroke="rgba(47,107,255,0.22)" strokeWidth="1" fill="none" />
        <ellipse cx="200" cy="200" rx="130" ry="44"
          stroke="rgba(47,107,255,0.16)" strokeWidth="1" fill="none" />
        {/* orbiting dot */}
        <circle cx="380" cy="200" r="4" fill="#2f6bff" opacity="0.9" />
      </motion.svg>

      {/* ═══════════════ HERO ═══════════════ */}
      <section className="hp-hero">
        <motion.h1
          className="hp-title"
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.75, delay: 0.25 }}
        >
          SPHER<span className="hp-title-x">Ex</span> SKY<br />
          <span className="hp-title-accent">TIME MACHINE</span>
        </motion.h1>

        <motion.p
          className="hp-subtitle"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, delay: 0.45 }}
        >
          Multi-epoch infrared explorer · 102-band spectrophotometry ·
          spot what moves and what changes
        </motion.p>

        <motion.div
          className="hp-cta-row"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.6 }}
        >
          <button
            type="button"
            className="hp-btn ghost"
            onClick={() => onLaunch()}
          >
            Launch Time Machine
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </motion.div>
      </section>

      {/* ═══════════════ STATS ═══════════════ */}
      <motion.section
        className="hp-stats"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-80px' }}
      >
        {STATS.map(s => (
          <motion.div key={s.label} className="hp-stat" variants={fadeItem}>
            <div className="hp-stat-num">{s.num}</div>
            <div className="hp-stat-label">{s.label}</div>
            <div className="hp-stat-sub">{s.sub}</div>
          </motion.div>
        ))}
      </motion.section>

      {/* ═══════════════ FEATURES ═══════════════ */}
      <motion.section
        className="hp-features"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-60px' }}
      >
        {FEATURES.map(f => (
          <motion.div key={f.title} className="hp-feat" variants={fadeItem}
            whileHover={{ y: -4, borderColor: 'rgba(47,107,255,0.6)' }}
            transition={{ type: 'spring', stiffness: 260, damping: 20 }}
          >
            <div className="hp-feat-icon">{f.icon}</div>
            <div className="hp-feat-title">{f.title}</div>
            <div className="hp-feat-desc">{f.desc}</div>
          </motion.div>
        ))}
      </motion.section>

      {/* ═══════════════ TARGETS ═══════════════ */}
      <motion.section
        className="hp-targets"
        variants={fadeUp}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-60px' }}
      >
        <div className="hp-section-header">
          <div className="hp-section-label">CURATED BENCHMARK TARGETS</div>
          <p className="hp-section-desc">
            Explore the 5 official NASA targets: Planet X analog WISE 0855, rapid proper-motion movers, and extreme variable stars.
          </p>
        </div>
        <div className="hp-target-scroll">
          {TARGETS.map(t => (
            <motion.button
              key={t.slug}
              type="button"
              className="hp-target-pill"
              onClick={() => onSelectTarget ? onSelectTarget(t) : onLaunch(t.slug)}
              whileHover={{ scale: 1.05, backgroundColor: 'rgba(47,107,255,0.18)' }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 300, damping: 22 }}
            >
              <span className="hp-pill-tag">{t.tag}</span>
              <span className="hp-pill-name">{t.label}</span>
              <span className="hp-pill-arrow">→</span>
            </motion.button>
          ))}
        </div>
      </motion.section>

      {/* ═══════════════ FOOTER CTA ═══════════════ */}
      <motion.section
        className="hp-footer-cta"
        variants={fadeUp}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-40px' }}
      >
        <p className="hp-footer-label">Ready to explore infrared space?</p>
        <button
          type="button"
          className="hp-btn primary"
          onClick={() => onLaunch()}
        >
          Launch Interactive Time Machine 🚀
        </button>
      </motion.section>
    </div>
  )
}
