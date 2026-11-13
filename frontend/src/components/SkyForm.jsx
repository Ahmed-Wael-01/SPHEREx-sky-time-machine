import { useEffect, useState } from 'react'
import { TARGETS } from '../lib/targets.js'
import { parseRA, parseDec } from '../lib/coords.js'

export default function SkyForm({ query, fov, onFov, maxFov, onSubmit }) {
  const [ra, setRa] = useState(String(query.ra))
  const [dec, setDec] = useState(String(query.dec))
  const [err, setErr] = useState(null)

  useEffect(() => {
    setRa(String(query.ra))
    setDec(String(query.dec))
  }, [query])

  const submit = (e) => {
    e.preventDefault()
    const r = parseRA(ra)
    const d = parseDec(dec)
    if (Number.isNaN(r)) return setErr('RA: degrees (0–360) or hours like 08h55m10.8s')
    if (Number.isNaN(d)) return setErr('Dec: degrees (−90 to 90) or like −07°14′42″')
    setErr(null)
    onSubmit({ ra: r, dec: d, fov: Number(fov) })
  }

  const pick = (t) => onSubmit({ target: t.slug, ra: t.ra, dec: t.dec, fov: t.fov })

  return (
    <section className="form">
      <form onSubmit={submit} className="coords">
        <label>
          RA
          <input value={ra} onChange={(e) => setRa(e.target.value)} placeholder="133.795 or 08h55m10.8s" />
        </label>
        <label>
          Dec
          <input value={dec} onChange={(e) => setDec(e.target.value)} placeholder="-7.245 or -07:14:42.5" />
        </label>
        <label className="fov">
          Field of view <b>{fov.toFixed(2)}°</b>{' '}
          <small>({Math.round(fov * 60)}′{maxFov && fov >= maxFov - 0.001 ? ', whole photo' : ''})</small>
          <input type="range" min="0.03" max={maxFov ? maxFov.toFixed(3) : 1} step="0.001"
            value={maxFov ? Math.min(fov, maxFov) : fov} onChange={(e) => onFov(Number(e.target.value))} />
        </label>
        <button type="submit" className="go">Show</button>
      </form>
      {err && <p className="form-err">{err}</p>}
      <div className="targets">
        {TARGETS.map((t) => (
          <button key={t.slug} className={query.target === t.slug ? 'on' : ''} onClick={() => pick(t)}>{t.label}</button>
        ))}
      </div>
    </section>
  )
}
