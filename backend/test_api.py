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
    s = c.get("/api/spectrum?ra=133.795&dec=-7.245").json
    assert s["points"][0].keys() >= {"wavelength_um", "flux_mjy", "err_mjy", "date", "detector", "flagged"}
    d = c.get("/api/detections?target=mock").json
    assert d["source"] == "mock" and d["candidates"]


def test_no_path_traversal():
    assert c.get("/data/../backend/app.py").status_code == 404


def test_unbaked_target_404():
    r = c.get("/api/frames?target=nope")
    assert r.status_code == 404 and r.json["error"] == "not_baked"
