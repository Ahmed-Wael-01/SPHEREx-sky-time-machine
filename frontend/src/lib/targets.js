// Keep in sync with science/targets.json (the pipeline's source of truth).
export const TARGETS = [
  { slug: 'wise0855', label: 'WISE 0855', ra: 133.795129, dec: -7.245147, fov: 0.5 },
  { slug: 'barnards-star', label: "Barnard's Star", ra: 269.452076, dec: 4.693364, fov: 0.5 },
  { slug: 'eps-indi-b', label: 'Epsilon Indi B', ra: 331.0438, dec: -56.7828, fov: 0.5 },
  { slug: 'rw-aur', label: 'RW Aurigae', ra: 76.956, dec: 30.401, fov: 0.5 },
  { slug: 'r-dra', label: 'R Draconis', ra: 248.1675, dec: 66.755, fov: 0.5 },
]

export const MOCK_TARGET = { slug: 'mock', label: 'Synthetic test', ra: 133.795, dec: -7.245, fov: 0.2 }

// Shown when the URL has no position. Switch to 'wise0855' once real frames are baked.
export const DEFAULT_TARGET = 'wise0855'
