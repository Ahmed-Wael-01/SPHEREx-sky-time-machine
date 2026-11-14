#!/usr/bin/env python3
"""Find positive source candidates above the noise in SPHEREx difference stacks.

    python science/mover_finder.py --target mock
    python science/mover_finder.py --target barnards-star --threshold 5

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, help='Target slug in the manifest')
    parser.add_argument('--threshold', type=float, default=5.0)
    parser.add_argument('--output', type=Path, help='Output JSON path')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.target):
        parser.error('--target must be a single target slug')
    if not math.isfinite(args.threshold) or args.threshold <= 0:
        parser.error('--threshold must be positive and finite')

    web = REPO / 'frontend' / 'public' / 'data' / args.target
    science = REPO / 'science' / 'output' / args.target
    output = args.output or science / 'detections.json'
    try:
        manifest = json.loads((web / 'manifest.json').read_text(encoding='utf-8'))
        result = detect(science / 'stacks.fits', manifest, args.threshold)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f'{result["frames_scanned"]} frames, {len(result["candidates"])} peaks -> {output}')


if __name__ == '__main__':
    main()
