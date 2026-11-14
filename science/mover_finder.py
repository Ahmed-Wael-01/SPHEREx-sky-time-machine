#!/usr/bin/env python3
"""Find positive source candidates above the noise in SPHEREx difference stacks.

    python science/mover_finder.py --target mock
    python science/mover_finder.py --target barnards-star --threshold 5
    python science/mover_finder.py --target barnards-star --known --publish   # the website's detections.json

Use the aligned stacks produced by fetch_cutouts.py, which masks flagged
pixels before stacking. A candidate is a peak in a difference image, so a
single detection cannot distinguish a moving source from a variable one.
"""
import argparse
import json
import math
from pathlib import Path
import re

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

from fetch_cutouts import REPO, robust_sigma


DIFFERENCE_HDU = re.compile(r'DIFF_E(\d+)_D([1-6])')


def find_peaks(image, threshold):
    finite = image[np.isfinite(image)]
    if not finite.size or finite.min() == finite.max():
        return []

    background = float(np.median(finite))
    noise = robust_sigma(finite)
    peaks = []
    suppressed = np.zeros(image.shape, dtype=bool)
    rows, cols = np.where(np.isfinite(image) & (image > background + threshold * noise))
    height, width = image.shape
    for idx in np.argsort(-image[rows, cols], kind='stable'):
        y, x = int(rows[idx]), int(cols[idx])
        if suppressed[y, x]:
            continue
        # Require the peak to extend to a neighbouring pixel. This rejects
        # isolated spikes without imposing a calibrated PSF model.
        local = image[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
        if np.count_nonzero(local > background + 2 * noise) < 2:
            continue
        y0, y1 = max(y - 2, 0), min(y + 3, height)
        x0, x1 = max(x - 2, 0), min(x + 3, width)
        suppressed[y0:y1, x0:x1] = True
        snr = float((image[y, x] - background) / noise)
        peaks.append((x, y, snr))
    return peaks


def detect(stacks, manifest, threshold=5.0):
    visits = {(v['epoch'], v['detector']): v for v in manifest['visits']}
    candidates = []
    frames = 0
    with fits.open(stacks) as hdus:
        for hdu in hdus:
            match = DIFFERENCE_HDU.fullmatch(hdu.name)
            if not match:
                continue
            epoch, detector = map(int, match.groups())
            visit = visits[(epoch, detector)]
            frames += 1
            height, width = hdu.data.shape
            wcs = WCS(hdu.header).celestial
            for x, y, snr in find_peaks(hdu.data, threshold):
                ra, dec = map(float, wcs.pixel_to_world_values(x, y))
                candidates.append({
                    'ra': ra, 'dec': dec, 'fx': (x + 0.5) / width,
                    'fy': 1 - (y + 0.5) / height, 'x': x, 'y': y,
                    'epoch': epoch, 'date': visit['date'], 'detector': detector,
                    'snr': snr, 'score': 1 - threshold / snr, 'kind': 'candidate',
                })
    if not frames:
        raise ValueError('No per-detector DIFF extensions found in the FITS file.')
    candidates.sort(key=lambda candidate: candidate['snr'], reverse=True)
    return {
        'target': manifest['target'], 'ra': manifest['ra'], 'dec': manifest['dec'],
        'fov': manifest['fov'], 'source': 'mock' if manifest['target'] == 'mock' else 'prebaked',
        'threshold_sigma': threshold, 'frames_scanned': frames,
        'note': ('Positive peaks with neighbouring signal. Motion is unverified. '
                 'Score ranks the excess above threshold and is not a probability.'),
        'candidates': candidates, 'variability': [],
    }


def match_known(result, manifest, radius_px=2.0, detectors=(5, 6)):
    """Known-mover check: in each 4-5 um difference image (D5, D6), is there a peak within radius_px of the
    target's predicted position (catalogue position + proper motion)? Keeps only those matches as
    candidates and counts every other peak as unmatched (unvetted). This is what the website shows."""
    width = height = manifest['pixels']
    by_image = {}
    for c in result['candidates']:
        by_image.setdefault((c['epoch'], c['detector']), []).append(c)
    matched, images = [], []
    for v in sorted(manifest['visits'], key=lambda v: (v['detector'], v['epoch'])):
        if v['detector'] not in detectors or not v.get('predicted'):
            continue
        p = v['predicted']
        peaks = by_image.get((v['epoch'], v['detector']), [])
        dist = [math.hypot((c['fx'] - p['fx']) * width, (c['fy'] - p['fy']) * height) for c in peaks]
        best = min(range(len(peaks)), key=dist.__getitem__) if peaks else None
        found = best is not None and dist[best] <= radius_px
        if found:
            c = dict(peaks[best])
            c.update(kind='mover', known_match=manifest.get('name', manifest['target']),
                     pm_mas_yr=manifest.get('pm_mas_yr'), offset_px=round(dist[best], 3))
            matched.append(c)
        images.append({'epoch': v['epoch'], 'detector': v['detector'], 'date': v['date'], 'found': found,
                       'unmatched_peaks': len(peaks) - (1 if found else 0)})
    n_unmatched = [i['unmatched_peaks'] for i in images]
    result.update(
        candidates=matched,
        evaluation={'recovered': bool(images) and all(i['found'] for i in images),
                    'found': sum(i['found'] for i in images), 'images_checked': len(images),
                    'exposures_used': sum(v['n_exposures'] for v in manifest['visits']
                                          if v['detector'] in detectors),
                    'threshold_sigma': result['threshold_sigma'], 'matching_radius_px': radius_px,
                    'unmatched_peaks_per_image_mean': round(float(np.mean(n_unmatched)), 3) if n_unmatched else None,
                    'images': images},
        note=('Recovers known movers in D5/D6 difference frames: candidates are peaks within '
              f'{radius_px:g} px of the predicted position. Unmatched peaks are unvetted and can include '
              'other real sources or leftovers of stars.'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, help='Target slug in the manifest')
    parser.add_argument('--threshold', type=float, default=5.0)
    parser.add_argument('--output', type=Path, help='Output JSON path')
    parser.add_argument('--known', action='store_true',
                        help='keep only peaks matching the target\'s predicted position (known-mover check)')
    parser.add_argument('--radius', type=float, default=2.0, help='match radius in pixels for --known')
    parser.add_argument('--publish', action='store_true',
                        help='write to frontend/public/data/<target>/detections.json (needs --known)')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.target):
        parser.error('--target must be a single target slug')
    if not math.isfinite(args.threshold) or args.threshold <= 0:
        parser.error('--threshold must be positive and finite')

    web = REPO / 'frontend' / 'public' / 'data' / args.target
    science = REPO / 'science' / 'output' / args.target
    if args.publish and not args.known:
        parser.error('--publish needs --known: the website shows matched movers, not every raw peak')
    output = args.output or (web if args.publish else science) / 'detections.json'
    try:
        manifest = json.loads((web / 'manifest.json').read_text(encoding='utf-8'))
        result = detect(science / 'stacks.fits', manifest, args.threshold)
        if args.known:
            result = match_known(result, manifest, args.radius)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    if args.known:
        e = result['evaluation']
        print(f'{e["found"]} of {e["images_checked"]} D5/D6 images: target found within {args.radius:g} px; '
              f'{e["unmatched_peaks_per_image_mean"]} unmatched peaks per image -> {output}')
    else:
        print(f'{result["frames_scanned"]} frames, {len(result["candidates"])} peaks -> {output}')


if __name__ == '__main__':
    main()
