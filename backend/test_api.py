"""Run from backend/:  python -m pytest -q"""
import app as appmod

c = appmod.app.test_client()


def test_health():
    assert c.get("/api/health").json["ok"]


def test_frames_mock_target():
    r = c.get("/api/frames?target=mock")
    assert r.status_code == 200
    j = r.json
    assert j["visits"] and {"date", "detector", "image_url", "diff_url", "n_exposures", "flags"} <= set(j["visits"][0])
    assert c.get(j["visits"][0]["image_url"]).status_code == 200


def test_frames_unknown_position_404():
    r = c.get("/api/frames?ra=10&dec=10&fov=0.2")
    assert r.status_code == 404 and r.json["error"] == "not_baked"


def test_bad_params():
    assert c.get("/api/frames?ra=abc&dec=1").status_code == 400
    assert c.get("/api/frames?ra=10&dec=95").status_code == 400
    assert c.get("/api/frames?dec=1").status_code == 400


def test_spectrum_and_detections_shape():
    import json
    real = json.loads((appmod.DATA_DIR / "wise0855" / "spectrum.json").read_text())
    ra, dec = real["positions"][0]
    s = c.get(f"/api/spectrum?target=wise0855&ra={ra}&dec={dec}").json
    assert s["points"][0].keys() >= {"wavelength_um", "flux_mjy", "err_mjy", "date", "detector", "flagged"}
    far = c.get("/api/spectrum?target=wise0855&ra=133.70&dec=-7.30").json
    assert far["points"] == [] and "target itself" in far["note"]
    none = c.get("/api/spectrum?target=rw-aur&ra=76.956&dec=30.401").json
    assert none["points"] == [] and none["source"] == "none"
    assert c.get("/api/spectrum?target=mock&ra=133.795&dec=-7.245").json["source"] == "mock"
    d = c.get("/api/detections?target=mock").json
    assert d["source"] == "mock" and d["candidates"]


def test_no_path_traversal():
    assert c.get("/data/../backend/app.py").status_code == 404


def test_unbaked_target_404():
    r = c.get("/api/frames?target=nope")
    assert r.status_code == 404 and r.json["error"] == "not_baked"
