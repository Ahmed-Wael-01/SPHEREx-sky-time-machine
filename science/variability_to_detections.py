"""
science/variability_to_detections.py  -  rebuild detections.json from saved results (no downloads)

Reads  science/output/<slug>/variability_results.csv + variability_summary.json
Writes frontend/public/data/<slug>/detections.json in the docs/api.md shape
(keeps any existing 'candidates' already in that file).

    python science/variability_to_detections.py --slug rw-aur
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from variability import to_contract   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="rw-aur")
    a = ap.parse_args()
    out = f"science/output/{a.slug}"
    res = pd.read_csv(f"{out}/variability_results.csv")
    res["flagged"] = res["flagged"].astype(bool)
    summary = json.load(open(f"{out}/variability_summary.json"))
    man_path = f"frontend/public/data/{a.slug}/manifest.json"
    det_path = f"frontend/public/data/{a.slug}/detections.json"
    manifest = json.load(open(man_path)) if os.path.exists(man_path) else None
    existing = json.load(open(det_path)) if os.path.exists(det_path) else {}
    if isinstance(existing.get("variability"), dict):      # old shape from the first version
        existing = {k: v for k, v in existing.items() if k != "variability"}
    d = to_contract(res, summary, manifest, existing, 0.0, 0.0)
    json.dump(d, open(det_path, "w"), indent=2)
    print("wrote", det_path)
    print("keys:", sorted(d.keys()), "| variability items:", len(d["variability"]),
          "| candidates:", len(d["candidates"]))


if __name__ == "__main__":
    main()