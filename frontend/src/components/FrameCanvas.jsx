// Draws a frame with a colour map, or a 3-colour composite of three grey frames, on a canvas.
import { useEffect, useRef } from 'react'
import { gammaTable } from '../lib/colormaps.js'

const greyCache = new Map() // url -> Promise<{w, h, data: Uint8ClampedArray (grey)}>

export function loadGrey(url) {
  if (!url) return Promise.resolve(null)
  if (!greyCache.has(url)) {
    greyCache.set(
      url,
      new Promise((resolve) => {
        const img = new Image()
        img.onload = () => {
          const c = document.createElement('canvas')
          c.width = img.naturalWidth
          c.height = img.naturalHeight
          const ctx = c.getContext('2d', { willReadFrequently: true })
          ctx.drawImage(img, 0, 0)
          const rgba = ctx.getImageData(0, 0, c.width, c.height).data
          const g = new Uint8ClampedArray(c.width * c.height)
          const a = new Uint8ClampedArray(c.width * c.height)
          for (let i = 0; i < g.length; i++) {
            g[i] = rgba[i * 4]
            a[i] = rgba[i * 4 + 3] // 0 = no data (pipeline writes it transparent)
          }
          resolve({ w: c.width, h: c.height, data: g, alpha: a })
        }
        img.onerror = () => resolve(null)
        img.src = url
      }),
    )
  }
  return greyCache.get(url)
}

// Per-channel auto level for the composite: background (median) → 0, 99.5th percentile → 255.
function levels(g) {
  const hist = new Uint32Array(256)
  for (let i = 0; i < g.length; i++) hist[g[i]]++
  const pick = (q) => {
    let acc = 0
    const target = q * g.length
    for (let v = 0; v < 256; v++) {
      acc += hist[v]
      if (acc >= target) return v
    }
    return 255
  }
  const lo = pick(0.5)
  const hi = Math.max(pick(0.995), lo + 1)
  return (v) => Math.max(0, Math.min(255, ((v - lo) / (hi - lo)) * 255))
}

function average(imgs) {
  const ok = imgs.filter(Boolean)
  if (!ok.length) return null
  const n = ok[0].data.length
  const out = new Uint8ClampedArray(n)
  for (let i = 0; i < n; i++) {
    let s = 0
    for (const im of ok) s += im.data[i]
    out[i] = s / ok.length
  }
  const alpha = new Uint8ClampedArray(n)
  for (let i = 0; i < n; i++) alpha[i] = ok.some((im) => im.alpha[i]) ? 255 : 0
  return { w: ok[0].w, h: ok[0].h, data: out, alpha }
}

/**
 * single: { url, lut, gamma }  or  rgb: { r: [urls], g: [urls], b: [urls], gamma }
 * onGrey(greyImage) lets the parent read pixel values for the hover readout.
 */
export default function FrameCanvas({ single, rgb, onGrey, alt }) {
  const ref = useRef(null)
  const key = JSON.stringify(single ? [single.url, single.lutName, single.gamma] : [rgb?.r, rgb?.g, rgb?.b, rgb?.gamma])

  useEffect(() => {
    let cancelled = false
    async function draw() {
      const cv = ref.current
      if (!cv) return
      if (single) {
        const g = await loadGrey(single.url)
        if (cancelled || !g) return
        cv.width = g.w
        cv.height = g.h
        const ctx = cv.getContext('2d')
        const out = ctx.createImageData(g.w, g.h)
        const gt = gammaTable(single.gamma)
        for (let i = 0; i < g.data.length; i++) {
          const v = gt[g.data[i]] * 3
          out.data[i * 4] = single.lut[v]
          out.data[i * 4 + 1] = single.lut[v + 1]
          out.data[i * 4 + 2] = single.lut[v + 2]
          out.data[i * 4 + 3] = g.alpha[i]
        }
        ctx.putImageData(out, 0, 0)
        onGrey?.(g)
      } else if (rgb) {
        const [R, G, B] = await Promise.all(
          [rgb.r, rgb.g, rgb.b].map(async (urls) => average(await Promise.all(urls.map(loadGrey)))),
        )
        if (cancelled) return
        const base = R || G || B
        if (!base) return
        cv.width = base.w
        cv.height = base.h
        const ctx = cv.getContext('2d')
        const out = ctx.createImageData(base.w, base.h)
        const gt = gammaTable(rgb.gamma)
        const chans = [R, G, B].map((c) => (c ? { d: c.data, f: levels(c.data) } : null))
        for (let i = 0; i < base.data.length; i++) {
          for (let k = 0; k < 3; k++) {
            const c = chans[k]
            out.data[i * 4 + k] = c ? gt[Math.round(c.f(c.d[i]))] : 0
          }
          out.data[i * 4 + 3] = chans.some((c, k) => c && [R, G, B][k].alpha[i]) ? 255 : 0
        }
        ctx.putImageData(out, 0, 0)
        onGrey?.(null)
      }
    }
    draw()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return <canvas ref={ref} className="frame-canvas" role="img" aria-label={alt} />
}
