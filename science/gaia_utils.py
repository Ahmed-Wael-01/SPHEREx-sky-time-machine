"""Gaia DR3 cone search with fallbacks (VizieR mirror -> ESA Gaia -> IRSA)."""
import pandas as pd
import astropy.units as u


def _norm(df):
    low = {c.lower(): c for c in df.columns}
    pick = lambda *n: next((low[k] for k in n if k in low), None)
    g = lambda *n: df[pick(*n)] if pick(*n) else pd.Series([float("nan")] * len(df))
    out = pd.DataFrame({
        "Source": g("source_id", "source"), "RA_ICRS": g("ra", "ra_icrs"),
        "DE_ICRS": g("dec", "de_icrs"), "Gmag": g("phot_g_mean_mag", "gmag"),
        "VarFlag": g("phot_variable_flag", "varflag"),
        "pmRA": g("pmra"), "pmDE": g("pmdec")})
    out["VarFlag"] = out["VarFlag"].astype(str).str.strip().str.upper()
    return out


def gaia_cone(target, radius_deg):
    r = radius_deg * u.deg
    tries = []

    def vizier(server):
        def f():
            from astroquery.vizier import Vizier
            Vizier.VIZIER_SERVER = server
            v = Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag", "VarFlag", "pmRA", "pmDE"], row_limit=-1)
            return v.query_region(target, radius=r, catalog="I/355/gaiadr3")[0].to_pandas()
        return f

    def esa():
        from astroquery.gaia import Gaia
        Gaia.ROW_LIMIT = -1
        return Gaia.cone_search_async(target, radius=r).get_results().to_pandas()

    def irsa():
        from astroquery.ipac.irsa import Irsa
        return Irsa.query_region(target, catalog="gaia_dr3_source", spatial="Cone", radius=r).to_pandas()

    tries = [("vizier-cfa", vizier("vizier.cfa.harvard.edu")), ("esa-gaia", esa),
             ("irsa", irsa), ("vizier-cds", vizier("vizier.cds.unistra.fr"))]
    for name, f in tries:
        try:
            df = f()
            if len(df):
                print(f"Gaia catalogue from: {name} ({len(df)} rows)")
                return _norm(df)
        except Exception as e:
            print(f"   Gaia source {name} failed: {str(e)[:80]}")
    raise SystemExit("No Gaia catalogue source worked. Check internet / try again later.")
