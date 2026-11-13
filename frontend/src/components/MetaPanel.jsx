import { fmtRA, fmtDec } from '../lib/coords.js'

export default function MetaPanel({ manifest, frame, mode, det, wl }) {
  if (!manifest) return <div className="panel"><h3>Details</h3><p className="muted">Nothing loaded.</p></div>
  const flags = frame?.flags ? Object.entries(frame.flags).filter(([, v]) => v > 0) : []
  return (
    <div className="panel">
      <h3>{manifest.name}</h3>
      <dl>
        <dt>Centre</dt>
        <dd>{fmtRA(manifest.ra)} {fmtDec(manifest.dec)}<br /><small>{manifest.ra.toFixed(4)}°, {manifest.dec.toFixed(4)}°</small></dd>
        <dt>Field</dt><dd>{manifest.fov}° · {manifest.pixels}px at {manifest.pixel_scale_arcsec}″</dd>
        <dt>Data</dt><dd>{manifest.n_exposures} exposures · {manifest.n_epochs} sky passes</dd>
        <dt>Detector</dt><dd>{det === 0 ? 'All six combined' : det === 'long' ? 'D5 + D6 combined' : `D${det}`} · {wl[0].toFixed(2)}–{wl[1].toFixed(2)} µm</dd>
        {frame && mode !== 'deep' && (<><dt>Visit</dt><dd>{frame.date} (MJD {frame.mjd}) · {frame.n_exposures} exposures stacked</dd></>)}
        {mode === 'diff' && frame?.diff_sigma_mjysr && (<><dt>Diff scale</dt><dd>±5σ = ±{(5 * frame.diff_sigma_mjysr).toFixed(3)} MJy/sr · white = brighter now</dd></>)}
        {manifest.pm_mas_yr && (manifest.pm_mas_yr[0] || manifest.pm_mas_yr[1]) ? (
          <><dt>Proper motion</dt><dd>{manifest.pm_mas_yr[0].toFixed(0)}, {manifest.pm_mas_yr[1].toFixed(0)} mas/yr</dd></>
        ) : null}
      </dl>
      {frame && mode !== 'deep' && (
        <>
          <h4>Quality flags (pixel counts)</h4>
          {flags.length ? (
            <ul className="flags">{flags.map(([k, v]) => <li key={k}><span>{k}</span><b>{v}</b></li>)}</ul>
          ) : <p className="muted">No flagged pixels.</p>}
          <p className="muted small">Masked before stacking: {manifest.masked_flags?.join(', ')}</p>
        </>
      )}
      <p className="muted small">Source: {manifest.source}{manifest._via === 'static' ? ' (static files)' : ''} · built {manifest.generated}</p>
    </div>
  )
}
