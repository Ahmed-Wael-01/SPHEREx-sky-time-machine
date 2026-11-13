"""Fill small isolated holes in already-made website pictures, without re-processing the photos.

Same rule as fetch_cutouts.to_png (holes of at most SMALL_HOLE_PX pixels, fully surrounded by data,
painted with the median of their edge). Only the PNGs change; stacks.fits keeps the blanks.

    python science/fill_png_holes.py wise0855 barnards-star eps-indi-b rw-aur r-dra
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from fetch_cutouts import REPO, small_holes  # noqa: E402


def fill(path):
    a = np.array(Image.open(path))
    if a.ndim != 3 or a.shape[2] != 2:
        return 0
    g, alpha = a[..., 0].astype(float), a[..., 1]
    nan = alpha == 0
    small = small_holes(nan)
    if not small.any():
        return 0
    lab, n = ndimage.label(small)
    for k in range(1, n + 1):
        blob = lab == k
        rim = ndimage.binary_dilation(blob) & ~nan
        g[blob] = np.median(g[rim])
    a[..., 0] = np.clip(np.round(g), 0, 255).astype(np.uint8)
    a[..., 1][small] = 255
    Image.fromarray(a, "LA").save(path, optimize=True)
    return int(small.sum())


if __name__ == "__main__":
    for slug in sys.argv[1:]:
        total = sum(fill(p) for p in sorted((REPO / "frontend/public/data" / slug).glob("*.png")))
        print(f"{slug}: filled {total} pixels")
