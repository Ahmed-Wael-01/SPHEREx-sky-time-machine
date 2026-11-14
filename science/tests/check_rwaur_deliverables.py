import glob, json, os, py_compile, subprocess

OUT = "science/output/rw-aur"
DET = "frontend/public/data/rw-aur/detections.json"
fails = warns = 0


def ok(c, msg):
    global fails
    print(("[OK]   " if c else "[FAIL] ") + msg)
    fails += (not c)
    return c


def warn(msg):
    global warns
    print("[WARN] " + msg)
    warns += 1


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300).stdout.strip()
    except Exception as e:
        return f"ERR {e}"


bad = []
for f in glob.glob("science/*.py"):
    try:
        py_compile.compile(f, doraise=True)
    except Exception:
        bad.append(f)
ok(not bad, f"all science/*.py compile {bad if bad else ''}")
ok(os.path.exists("science/gaia_utils.py"), "science/gaia_utils.py exists")

req = open("requirements.txt").read().lower() if os.path.exists("requirements.txt") else ""
for pkg in ["pandas", "matplotlib", "astropy", "astroquery", "numpy"]:
    ok(pkg in req, f"requirements.txt lists {pkg}")

for name in ["rwaur_answer_key.csv", "rwaur_pair_results.csv", "rwaur_summary.json"]:
    ok(os.path.exists(f"{OUT}/{name}"), f"{OUT}/{name} exists")
if os.path.exists(f"{OUT}/rwaur_summary.json"):
    s = json.load(open(f"{OUT}/rwaur_summary.json"))
    ok(bool(s.get("slide_sentence")), "slide_sentence is filled")
    print("       ->", s.get("slide_sentence"))
    for c in s.get("epoch_pair_comparison", []):
        print("       pair", c.get("epoch_a"), "->", c.get("epoch_b"), c.get("spherex_direction"),
              c.get("spherex_change_pct"), "% | spread", c.get("pair_to_pair_spread_pct"), "%")
    if s.get("total_compared", 0) == 0:
        warn("no external comparison yet (need data/rwaur_external.csv, run with --external)")
if os.path.exists(f"{OUT}/rwaur_answer_key.csv"):
    import pandas as pd
    k = pd.read_csv(f"{OUT}/rwaur_answer_key.csv")
    if (k["n_ext_points"] < 3).any():
        warn("some epoch has < 3 external points: " + str(k["n_ext_points"].tolist()))
    else:
        ok(True, "every epoch has >= 3 external points: " + str(k["external_state"].tolist()))

vs = f"{OUT}/variability_summary.json"
if ok(os.path.exists(vs), f"{vs} exists"):
    v = json.load(open(vs))
    print("       -> variables caught:", v.get("heldout_variables_caught"), "of", v.get("heldout_variables"),
          "| false alarms:", v.get("heldout_false_alarms"), "of", v.get("heldout_steady"))
    if (v.get("heldout_variables") or 0) < 3:
        warn("fewer than 3 held-out variables: say 'prototype, tiny sample' on the slide (try --radius 0.4)")
if os.path.exists(DET):
    try:
        d = json.load(open(DET))
        ok("variability" in d, f"{DET} valid JSON with 'variability' (keys: {list(d)})")
    except Exception as e:
        ok(False, f"{DET} is valid JSON ({e})")
else:
    warn(f"{DET} not found (run variability.py --slug rw-aur)")

out = sh("cd backend && python -m pytest -q 2>&1 | tail -2")
ok("passed" in out and "failed" not in out, "backend tests: " + (out.splitlines()[-1] if out else "no output"))

print("\n--- git ---")
print(sh("git status -sb | head -12"))
ok(not sh("git ls-files science/cache science/output | head -3"), "science/cache and science/output are NOT tracked")
unpushed = sh("git log @{u}.. --oneline 2>/dev/null")
ok(not unpushed, "everything committed is pushed" + (f" (unpushed: {unpushed})" if unpushed else ""))

print(f"\nDone: {fails} failed, {warns} warnings.")