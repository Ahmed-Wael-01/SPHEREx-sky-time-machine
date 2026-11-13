// Colour lookup tables (256 x RGB) for the grey PNG frames, built from a few control colours.
// Frames stay grey on disk; colour is applied in the browser so switching is instant.

function lut(stops) {
  const out = new Uint8ClampedArray(256 * 3)
  const pts = stops.map(([t, hex]) => [t, parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)])
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    let k = 0
    while (k < pts.length - 2 && t > pts[k + 1][0]) k++
    const [t0, r0, g0, b0] = pts[k]
    const [t1, r1, g1, b1] = pts[k + 1]
    const f = t1 > t0 ? Math.min(1, Math.max(0, (t - t0) / (t1 - t0))) : 0
    out[i * 3] = r0 + (r1 - r0) * f
    out[i * 3 + 1] = g0 + (g1 - g0) * f
    out[i * 3 + 2] = b0 + (b1 - b0) * f
  }
  return out
}

// Sequential maps for normal frames
export const COLORMAPS = {
  grey: { label: 'Grey', lut: lut([[0, '#000000'], [1, '#ffffff']]) },
  heat: { label: 'Heat', lut: lut([[0, '#000000'], [0.35, '#b31b00'], [0.7, '#ffb21a'], [1, '#ffffff']]) },
  viridis: { label: 'Viridis', lut: lut([[0, '#440154'], [0.25, '#3b528b'], [0.5, '#21918c'], [0.75, '#5ec962'], [1, '#fde725']]) },
  inferno: { label: 'Inferno', lut: lut([[0, '#000004'], [0.2, '#420a68'], [0.4, '#932667'], [0.6, '#dd513a'], [0.8, '#fca50a'], [1, '#fcffa4']]) },
  blue: { label: 'Null Point blue', lut: lut([[0, '#000000'], [0.45, '#1f4fff'], [0.8, '#9db8ff'], [1, '#ffffff']]) },
}

// Diverging maps for difference frames: mid-grey (128) = no change
export const DIFF_COLORMAPS = {
  grey: { label: 'Grey', lut: lut([[0, '#000000'], [1, '#ffffff']]) },
  bluered: { label: 'Blue–red', lut: lut([[0, '#2f6bff'], [0.42, '#16213f'], [0.5, '#0a0a0a'], [0.58, '#4a1a10'], [1, '#ff5a1f']]) },
  bluewhitered: { label: 'Blue–white–red', lut: lut([[0, '#1f4fff'], [0.5, '#f5f5f5'], [1, '#e8341c']]) },
}

// Contrast: remap the grey level before colouring (gamma)
export const STRETCHES = {
  normal: { label: 'Normal', gamma: 1 },
  faint: { label: 'Boost faint', gamma: 0.6 },
  bright: { label: 'Bright only', gamma: 1.7 },
}

export function gammaTable(gamma) {
  const t = new Uint8ClampedArray(256)
  for (let i = 0; i < 256; i++) t[i] = Math.round(255 * Math.pow(i / 255, gamma))
  return t
}
