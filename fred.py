# fred.py
import os
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

def latest(series_id: str):
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("Missing env var: FRED_API_KEY")

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }

    r = requests.get(FRED_BASE, params=params, timeout=10)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if not obs:
        return None

    v = obs[0].get("value")
    if v in (None, ".", ""):
        return None
    try:
        return float(v)
    except:
        return None

def liquidity_snapshot():
    ids = {
        "SOFR": "SOFR",
        "EFFR": "EFFR",
        "IORB": "IORB",
        "RRP":  "RRPONTSYD",
        "TGA":  "WTREGEN",
        "RESERVES": "WRESBAL",
    }
    out = {}
    for k, sid in ids.items():
        out[k] = latest(sid)
    return out
