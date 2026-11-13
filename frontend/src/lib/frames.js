// Frames for the detector picker. Besides All (0) and D1..D6 there is "long": D5 + D6 together
// (about 3.8-5 um), where cold brown dwarfs like WISE 0855 glow and most stars are faint.
// The combined frame lists several image URLs; the canvas averages them.

export const LONG = 'long'
const LONG_DETS = [5, 6]

export function detectorChoices(manifest) {
  const dets = manifest?.detectors || [1, 2, 3, 4, 5, 6]
  const hasLong = LONG_DETS.some((d) => dets.includes(d))
  return [0, ...(hasLong ? [LONG] : []), ...dets]
}

function mergeFlags(list) {
  const out = {}
  for (const f of list) for (const [k, v] of Object.entries(f || {})) out[k] = (out[k] || 0) + v
  return out
}

export function framesFor(manifest, det) {
  const visits = manifest?.visits || []
  if (det !== LONG) return visits.filter((v) => v.detector === det).sort((a, b) => a.mjd - b.mjd)
  const byEpoch = new Map()
  for (const v of visits) {
    if (!LONG_DETS.includes(v.detector)) continue
    if (!byEpoch.has(v.epoch)) byEpoch.set(v.epoch, [])
    byEpoch.get(v.epoch).push(v)
  }
  const all = visits.filter((v) => v.detector === 0)
  return [...byEpoch.entries()].map(([epoch, vs]) => {
    const ref = all.find((v) => v.epoch === epoch) || vs[0]
    const wls = vs.flatMap((v) => v.wavelength_um || [])
    return {
      date: ref.date,
      mjd: ref.mjd,
      epoch,
      detector: LONG,
      image_url: vs.map((v) => v.image_url),
      diff_url: vs.map((v) => v.diff_url).filter(Boolean),
      n_exposures: vs.reduce((s, v) => s + v.n_exposures, 0),
      flags: mergeFlags(vs.map((v) => v.flags)),
      wavelength_um: wls.length ? [Math.min(...wls), Math.max(...wls)] : null,
      predicted: ref.predicted,
    }
  }).sort((a, b) => a.mjd - b.mjd)
}

export function deepFor(manifest, det) {
  const deep = manifest?.deep || []
  if (det !== LONG) return deep.find((d) => d.detector === det)
  const ds = deep.filter((d) => LONG_DETS.includes(d.detector))
  if (!ds.length) return undefined
  return { detector: LONG, image_url: ds.map((d) => d.image_url), n_exposures: ds.reduce((s, d) => s + d.n_exposures, 0) }
}

export function wavelengthFor(manifest, det, nominal) {
  if (det === LONG) {
    const a = manifest?.detector_wavelength_um?.[5] || nominal[5]
    const b = manifest?.detector_wavelength_um?.[6] || nominal[6]
    return [a[0], b[1]]
  }
  return manifest?.detector_wavelength_um?.[det] || (det ? nominal[det] : [0.75, 5.0])
}
