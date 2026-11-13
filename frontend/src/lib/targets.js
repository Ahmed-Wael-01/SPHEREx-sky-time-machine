// Keep in sync with science/targets.json (the pipeline's source of truth).
// det = the view a target opens in ('long' = 4-5 um, where brown dwarfs glow).
export const TARGETS = [
  {
    slug: 'wise0855',
    det: 'long',
    label: 'WISE 0855',
    tag: 'Planet X Analog',
    kind: 'mover',
    ra: 133.795129,
    dec: -7.245147,
    fov: 0.5,
    blurb: 'Coldest known brown dwarf (~250 K), ~8 arcsec/yr proper motion. Glows brightly in detectors 5-6 (4.5–5 µm).',
    tip: 'Opens in the 4–5 µm view where it glows. Watch the close-up box, or press First ↔ last: the dot moves west of the yellow marks.',
  },
  {
    slug: 'barnards-star',
    label: "Barnard's Star",
    tag: 'Speed Record',
    kind: 'mover',
    ra: 269.452076,
    dec: 4.693364,
    fov: 0.5,
    blurb: 'Fastest proper motion of any star (~10.3 arcsec/yr). Core stays saturated but unmasked without artifact holes.',
    tip: 'So bright it overloads the camera. Switch to Difference (Movers): the orange/blue pair flips between 2025 and 2026 as it moves north.',
  },
  {
    slug: 'eps-indi-b',
    det: 'long',
    label: 'Epsilon Indi B',
    tag: 'Binary Brown Dwarf',
    kind: 'mover',
    ra: 331.0438,
    dec: -56.7828,
    fov: 0.5,
    blurb: 'Nearby brown-dwarf binary pair Ba/Bb moving at ~4.7 arcsec/yr.',
    tip: 'Observe proper motion separation close to Epsilon Indi A.',
  },
  {
    slug: 'rw-aur',
    label: 'RW Aurigae',
    tag: 'Young Variable',
    kind: 'variable',
    ra: 76.956,
    dec: 30.401,
    fov: 0.5,
    blurb: 'Young stellar object with circumstellar dust obscuration causing dramatic multi-magnitude dimming events.',
    tip: 'Switch to Difference Mode to reveal strong residual flux variations and view the Light Curve.',
  },
  {
    slug: 'r-dra',
    label: 'R Draconis',
    tag: 'Mira Variable',
    kind: 'variable',
    ra: 248.1675,
    dec: 66.755,
    fov: 0.5,
    blurb: 'Pulsating asymptotic giant branch Mira star with vast cyclical brightness oscillations over months.',
    tip: 'Compare Sum Mode with individual visits to inspect the huge infrared amplitude swing.',
  },
]

export const MOCK_TARGET = {
  slug: 'mock',
  label: 'Synthetic test',
  tag: 'Offline Scaffolding',
  kind: 'test',
  ra: 133.795,
  dec: -7.245,
  fov: 0.2,
  blurb: 'Developer synthetic test field with simulated SPHEREx noise, movers, and bad pixels.',
  tip: 'Used for smoke testing offline when IRSA archive data is not cached.',
}

// Shown when the URL has no position.
export const DEFAULT_TARGET = 'wise0855'
